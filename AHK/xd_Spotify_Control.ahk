#Requires AutoHotkey v2.0
; Прямое управление: Voicemeeter DLL + PostMessage (Spotify) — без задержек.
; Discord (Python): опционально, только fire-and-forget HTTP, не блокирует клавиши.

#SingleInstance Force

; Функция чтения значения из .env файла
GetEnvValue(key, envPath := "") {
    if (envPath = "")
        envPath := A_ScriptDir "\..\.env"

    if !FileExist(envPath)
        return ""
    
    for line in StrSplit(FileRead(envPath, "UTF-8"), "`n", "`r") {
        line := Trim(line)
        if (line = "" || SubStr(line, 1, 1) = "#")
            continue
        
        parts := StrSplit(line, "=", , 2)
        if (parts.Length = 2 && Trim(parts[1]) = key) {
            return Trim(parts[2], ' "' "'")
        }
    }
    return ""
}

; --- Значения из .env, синхронизированные с config.py Python-бота ---
; ПОМЕНЯЙ ТУТ (или, лучше, в .env), если у тебя другие пути/порт/страйп:
global BRIDGE_TOKEN := GetEnvValue("BRIDGE_TOKEN")

global VM_DLL_PATH := GetEnvValue("VM_DLL_PATH")
if (VM_DLL_PATH = "")
    VM_DLL_PATH := "C:\Program Files (x86)\VB\Voicemeeter\VoicemeeterRemote64.dll"

global VM_STRIP_INDEX := GetEnvValue("VM_STRIP_INDEX")
if (VM_STRIP_INDEX = "")
    VM_STRIP_INDEX := "7"
global VM_GAIN_PARAM := "Strip[" VM_STRIP_INDEX "].Gain"
global VM_MUTE_PARAM := "Strip[" VM_STRIP_INDEX "].Mute"

; -60/12 dB — жёсткие пределы фейдера самого Voicemeeter (не личная настройка),
; но диапазон, в котором эта клавиатурная утилита позволяет крутить громкость,
; всё же можно сузить через .env, если хочешь.
global VM_MIN_DB := GetEnvValue("VM_MIN_DB")
if (VM_MIN_DB = "")
    VM_MIN_DB := -60
global VM_MAX_DB := GetEnvValue("VM_MAX_DB")
if (VM_MAX_DB = "")
    VM_MAX_DB := 12

; --- Voicemeeter (локально, мгновенно) ---
vmDLL := VM_DLL_PATH
hModule := DllCall("LoadLibrary", "Str", vmDLL, "Ptr")
if !hModule {
    MsgBox("Не удалось загрузить Voicemeeter DLL:`n" vmDLL "`n`nПровеь путь VM_DLL_PATH в .env.", "xd_Spotify_Control", "Icon!")
    ExitApp()
}
DllCall(vmDLL "\VBVMR_Login")

global isMuted := false
global currentVolume := 0.0
global lastInteraction := 0

; --- Опциональная синхронизация Discord (ВЫКЛ = как оригинал) ---
global SYNC_DISCORD := true

; Порт моста синхронизирован с WEB_PORT из .env бота — если поменяешь один,
; поменяй и другой (или просто задай WEB_PORT в .env один раз, оба места
; читают отсюда же).
global WEB_PORT := GetEnvValue("WEB_PORT")
if (WEB_PORT = "")
    WEB_PORT := "5000"
global PY_BASE := "http://127.0.0.1:" WEB_PORT

SetTimer(SyncWithVoicemeeter, 200)

SyncWithVoicemeeter() {
    global currentVolume, isMuted, lastInteraction, vmDLL, VM_GAIN_PARAM, VM_MUTE_PARAM
    if (A_TickCount - lastInteraction < 1000)
        return
    if (DllCall(vmDLL "\VBVMR_IsParametersDirty") > 0) {
        buf := Buffer(4)
        if (DllCall(vmDLL "\VBVMR_GetParameterFloat", "AStr", VM_GAIN_PARAM, "Ptr", buf) = 0)
            currentVolume := NumGet(buf, "Float")
        if (DllCall(vmDLL "\VBVMR_GetParameterFloat", "AStr", VM_MUTE_PARAM, "Ptr", buf) = 0)
            isMuted := !!NumGet(buf, "Float")
    }
}

; --- Горячие клавиши (только локальные вызовы) ---

Numpad0:: {
    global isMuted := !isMuted, lastInteraction := A_TickCount, vmDLL, VM_MUTE_PARAM
    DllCall(vmDLL "\VBVMR_SetParameterFloat", "AStr", VM_MUTE_PARAM, "Float", Float(isMuted))
    NotifyDiscordAsync("muted", isMuted)
}

NumpadAdd:: ChangeVolume(0.5)
NumpadSub:: ChangeVolume(-0.5)

ChangeVolume(delta) {
    global vmDLL, VM_GAIN_PARAM, VM_MIN_DB, VM_MAX_DB, lastInteraction := A_TickCount
    global currentVolume := Max(VM_MIN_DB, Min(VM_MAX_DB, currentVolume + delta))
    DllCall(vmDLL "\VBVMR_SetParameterFloat", "AStr", VM_GAIN_PARAM, "Float", Float(currentVolume))
    NotifyDiscordAsync("volume", currentVolume)
}

NumpadEnter:: {
    if WinExist("ahk_exe Spotify.exe")
        PostMessage(0x0319, 0, 0xE0000, , "ahk_exe Spotify.exe")
    NotifyDiscordAsync("track")
}

NumpadDot:: {
    if IsAdPlaying() {
        RestartSpotify()
    } else {
        if WinExist("ahk_exe Spotify.exe")
            PostMessage(0x0319, 0, 0xB0000, , "ahk_exe Spotify.exe")
        NotifyDiscordAsync("track")
    }
}

NumpadMult:: {
    if WinExist("ahk_exe Spotify.exe")
        PostMessage(0x0319, 0, 0xC0000, , "ahk_exe Spotify.exe")
    NotifyDiscordAsync("track")
}

; --- Определение рекламы: во время рекламы заголовок окна не содержит " - " ---
IsAdPlaying() {
    if !WinExist("ahk_exe Spotify.exe")
        return false
    title := WinGetTitle("ahk_exe Spotify.exe")
    return !InStr(title, " - ") || InStr(title, "Spotify Free") = 1 || title = "Spotify"
}

; --- Общая функция перезапуска Spotify (используется и в #^4, и в NumpadDot при рекламе) ---
RestartSpotify() {
    activeWin := WinGetID("A")
    title := WinGetTitle("ahk_exe Spotify.exe")
    wasPlaying := InStr(title, " - ")
        && !InStr(title, "Spotify - ")
        && !InStr(title, "Spotify Free")

    RunWait("taskkill /F /IM Spotify.exe", , "Hide")
    Run(A_AppData "\Spotify\Spotify.exe", , "Min")

    if WinWait("ahk_exe Spotify.exe", , 5) {
        if (MonitorGetCount() >= 2) {
            MonitorGet(2, &L, &T)
            WinMove(L, T, , , "ahk_exe Spotify.exe")
            WinMaximize("ahk_exe Spotify.exe")
        }
        if WinExist("ahk_id " activeWin)
            WinActivate("ahk_id " activeWin)
        if wasPlaying
            PostMessage(0x0319, 0, 0xE0000, , "ahk_exe Spotify.exe")
        NotifyDiscordAsync("track")
    }
}

#HotIf WinExist("ahk_exe Spotify.exe")
#^4:: {
    RestartSpotify()
}
#HotIf

; Fire-and-forget: Async=true, ответ не ждём, таймауты минимальные.
NotifyDiscordAsync(kind, value := "") {
    global SYNC_DISCORD, PY_BASE, BRIDGE_TOKEN
    if !SYNC_DISCORD
        return
    payload := "{}"
    if (kind = "volume")
        payload := Format('{{"volume":{1}}}', value)
    else if (kind = "muted")
        payload := Format('{{"muted":{1}}}', value ? "true" : "false")
    else if (kind = "track") {
        title := WinExist("ahk_exe Spotify.exe") ? WinGetTitle("ahk_exe Spotify.exe") : ""
        active := (title != "" && title != "Spotify" && title != "Spotify Free")
        payload := Format(
            '{{"track_title":"{1}","track_active":{2}}}',
            JsonEscape(title),
            active ? "true" : "false"
        )
    }
    try {
        req := ComObject("WinHttp.WinHttpRequest.5.1")
        req.Open("POST", PY_BASE "/ahk/presence_notify", true)
        req.SetRequestHeader("Content-Type", "application/json; charset=utf-8")
        req.SetRequestHeader("X-Bridge-Token", BRIDGE_TOKEN)
        req.SetTimeouts(50, 50, 100, 100)
        req.Send(payload)
    } catch {
    }
}

JsonEscape(str) {
    str := StrReplace(str, "\", "\\")
    str := StrReplace(str, '"', '\"')
    return str
}

OnExit(ExitFunc)
ExitFunc(*) {
    global vmDLL
    try DllCall(vmDLL "\VBVMR_Logout")
}
