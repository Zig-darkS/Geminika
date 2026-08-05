"""Application configuration, constants, and localization."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Final, Mapping, MutableMapping, Union

import discord
from dotenv import load_dotenv
load_dotenv()

# --- Paths ---
BASE_DIR: Final[Path] = Path(__file__).resolve().parent
DATA_DIR: Final[Path] = BASE_DIR / "data"
SETTINGS_FILE: Final[Path] = DATA_DIR / "BotSettings.json"
EXPORT_ROOT: Final[Path] = BASE_DIR / "exports"  # общий корень для exporter.py и profile_tracker.py

DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_discord_token() -> str:
    env_token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if env_token:
        return env_token
    token_file = DATA_DIR / "token.txt"
    if token_file.is_file():
        try:
            return token_file.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return ""


# --- Discord ---
DISCORD_BOT_TOKEN: Final[str] = _load_discord_token()
DISCORD_BOT_OWNER_ID: Final[int] = int(os.environ.get("DISCORD_BOT_OWNER_ID", "0"))
COMMAND_PREFIX: Final[str] = os.environ.get("COMMAND_PREFIX", "!")

# "ru" или "default" (английский) — какой язык использовать, когда локаль
# определить не получается (например, в !-командах вне слэш-интеракций).
DEFAULT_LOCALE: Final[str] = (
    "ru" if os.environ.get("DEFAULT_LOCALE", "ru").strip().lower().startswith("ru")
    else "default"
)

# --- AHK bridge auth (пусто = проверка выключена) ---
BRIDGE_TOKEN: Final[str] = os.environ.get("BRIDGE_TOKEN", "").strip()


# --- Voicemeeter ---
def _resolve_vm_dll_path() -> Path:
    """VM_DLL_PATH из .env побеждает; иначе перебираем типичные варианты
    установки (обычный Voicemeeter / Banana / Potato, с (x86) и без)."""
    override = os.environ.get("VM_DLL_PATH", "").strip()
    if override:
        return Path(override)

    candidates = [
        r"C:\Program Files (x86)\VB\Voicemeeter\VoicemeeterRemote64.dll",
        r"C:\Program Files\VB\Voicemeeter\VoicemeeterRemote64.dll",
        r"C:\Program Files (x86)\VB\Voicemeeter\VoicemeeterRemote.dll",
        r"C:\Program Files\VB\Voicemeeter\VoicemeeterRemote.dll",
    ]
    for c in candidates:
        p = Path(c)
        if p.is_file():
            return p
    # Ничего не нашли на диске — возвращаем исторический дефолт, чтобы
    # существующая проверка "DLL не найдена" в voicemeeter_client.py
    # сработала с осмысленным путём в сообщении об ошибке.
    return Path(candidates[0])


VM_DLL_PATH: Final[Path] = _resolve_vm_dll_path()
VM_STRIP_INDEX: Final[int] = int(os.environ.get("VM_STRIP_INDEX", "7"))

# ВАЖНО: -60.0 / 12.0 — это НЕ личное предпочтение, а собственные жёсткие
# пределы фейдера страйпа/шины в самом Voicemeeter (физически дальше слайдер
# не двигается ни в одной редакции — Basic/Banana/Potato). Менять их имеет
# смысл только если хочешь сузить диапазон *бота* внутри этих границ;
# выставить шире -60/12 бессмысленно — Voicemeeter всё равно обрежет сам.
VM_MIN_DB: Final[float] = float(os.environ.get("VM_MIN_DB", "-60.0"))
VM_MAX_DB: Final[float] = float(os.environ.get("VM_MAX_DB", "12.0"))

# --- Audio / streaming ---
_vm_output_device_env = os.environ.get("VM_OUTPUT_DEVICE", "").strip()
if not _vm_output_device_env:
    raise RuntimeError(
        "VM_OUTPUT_DEVICE не задан в .env. Это должно быть ТОЧНОЕ имя "
        "виртуального выхода Voicemeeter (посмотри в Windows: Звук -> "
        "Запись/Воспроизведение). Для Banana это обычно "
        "'Voicemeeter Out B2 (VB-Audio Voicemeeter VAIO)', но для обычного "
        "Voicemeeter или Potato имя другое — раньше бот тихо подставлял "
        "чужой дефолт и стрим не запускался без единого понятного сообщения."
    )
VM_OUTPUT_DEVICE: Final[str] = _vm_output_device_env

# ffmpeg-параметры для радио-стрима (start_radio в bot_instance.py).
# Дефолты рассчитаны на низкую задержку при локальном захвате;
# подстрой под своё железо/сеть через .env, если нужно.
FFMPEG_BEFORE_ARGS: Final[str] = os.environ.get(
    "FFMPEG_BEFORE_ARGS", "-f dshow -rtbufsize 100M -audio_buffer_size 50"
)
FFMPEG_AFTER_ARGS: Final[str] = os.environ.get(
    "FFMPEG_AFTER_ARGS",
    "-vn -ac 2 -ar 48000 -threads 1 -preset ultrafast -tune zerolatency",
)

# --- HTTP bridge (AHK -> Python) ---
WEB_HOST: Final[str] = os.environ.get("WEB_HOST", "127.0.0.1")
WEB_PORT: Final[int] = int(os.environ.get("WEB_PORT", "5000"))
WEB_BASE_URL: Final[str] = f"http://{WEB_HOST}:{WEB_PORT}"

# --- Multimedia (Win32) ---
WM_APPCOMMAND: Final[int] = 0x0319
MEDIA_NEXT: Final[int] = 0xB0000
MEDIA_PLAY_PAUSE: Final[int] = 0xE0000
MEDIA_PREV: Final[int] = 0xC0000


def _load_idle_titles() -> frozenset[str]:
    """Базовый набор + всё, что пользователь добавил через
    SPOTIFY_IDLE_TITLES_EXTRA (через запятую) в .env — нужно для
    не-русских клиентов Spotify, у которых заголовок-заглушка не
    'Музыка без помех', а что-то на их языке."""
    base = {"Spotify", "Spotify Free", "Музыка без помех", ""}
    extra = os.environ.get("SPOTIFY_IDLE_TITLES_EXTRA", "")
    for title in extra.split(","):
        title = title.strip()
        if title:
            base.add(title)
    return frozenset(base)


SPOTIFY_IDLE_TITLES: Final[frozenset[str]] = _load_idle_titles()

# --- Громкость / presence — тюнинг ---
VOLUME_STEP_DB: Final[float] = float(os.environ.get("VOLUME_STEP_DB", "2.0"))
PRESENCE_UPDATE_INTERVAL_SECONDS: Final[int] = int(
    os.environ.get("PRESENCE_UPDATE_INTERVAL_SECONDS", "15")
)
EMBED_COLOR: Final[int] = int(
    os.environ.get("EMBED_COLOR", "1DB954"), 16  # зелёный Spotify по умолчанию
)

# Кривая фейда громкости (vm_fade_volume в bot_instance.py): шаг в dB,
# максимум шагов и пауза между ними. Раньше было "на глаз" зашито в методе.
FADE_STEP_DB: Final[float] = float(os.environ.get("FADE_STEP_DB", "0.5"))
FADE_MAX_STEPS: Final[int] = int(os.environ.get("FADE_MAX_STEPS", "20"))
FADE_STEP_DELAY_SECONDS: Final[float] = float(
    os.environ.get("FADE_STEP_DELAY_SECONDS", "0.05")
)

# --- Default persisted settings ---
DEFAULT_SETTINGS: Final[dict[str, Any]] = {
    "volume_ceiling": float(os.environ.get("VOLUME_CEILING_DEFAULT", "-4.0")),
    "auto_join": True,
    "auto_leave": True,
    "allow_others_vc": False,
    "status_msg_id": None,
    "status_channel_id": None,
    "status_enabled": False,
    "only_owner_mode": False,
}

_settings_lock = threading.RLock()
_bot_settings: dict[str, Any] = dict(DEFAULT_SETTINGS)

_TRANSLATIONS: Final[dict[str, dict[str, str]]] = {
    "ru": {
        "paused": "⏸️ Переключено: Пауза / Воспроизведение",
        "skipped": "⏭️ Следующий трек",
        "prev": "⏮️ Вернуть на начало трека ( или предыдущий трек )",
        "prev2": "⏮️⏮️ Предыдущий трек ( или 2 трека назад? )",
        "not_found": "⚠️ Spotify не найден.",
        "owner_not_in_vc": "❌ Хозяин плеера не в голосовом канале!",
        "join_same_vc": "❌ Зайди в тот же канал к хозяину!",
        "joined": "🔊 Подключился к каналу!",
        "left": "🔇 Вышел из канала.",
        "vol_update": "🔊 Громкость Strip[7]: {v} dB",
        "muted": "🔇 Звук выключен (Muted)",
        "unmuted": "🔊 Звук включен (Unmuted)",
        "vlimit_set": "🛡️ Потолок громкости установлен на: {v} dB",
        "no_permission": "❌ У тебя нет прав для этой команды.",
        "nothing_playing": "Ничего не играет",
        "now_playing": "Сейчас играет",
        "volume_bar": "Громкость",
        "setting_updated": "✅ Настройка обновлена: {name} = {val}",
        "join_auto": "Авто-вход",
        "leave_auto": "Авто-выход",
        "others_access": "Доступ другим",
        "status_msg_on": "🔔 Живой статус включен в этом канале.",
        "status_msg_off": "🔕 Живой статус выключен.",
        "vol_up": "Громче",
        "vol_down": "Тише",
        "commands_toggle": "Режим только овнера",
        "no_permission_commands": "❌ Команды временно отключены владельцем.",
    },
    "default": {
        "paused": "⏸️ Toggle Play / Pause",
        "skipped": "⏭️ Next track",
        "prev": "⏮️ Track start ( or previous track )",
        "prev2": "⏮️⏮️ Previous track ( or 2 tracks back? )",
        "not_found": "⚠️ Spotify not found.",
        "owner_not_in_vc": "❌ Owner is not in a voice channel!",
        "join_same_vc": "❌ Join the owner's voice channel!",
        "joined": "🔊 Joined the voice channel!",
        "left": "🔇 Left the voice channel.",
        "vol_update": "🔊 Strip[7] volume: {v} dB",
        "muted": "🔇 Muted",
        "unmuted": "🔊 Unmuted",
        "vlimit_set": "🛡️ Volume ceiling set to: {v} dB",
        "no_permission": "❌ You don't have permission to use this.",
        "nothing_playing": "Nothing is playing",
        "now_playing": "Now Playing",
        "volume_bar": "Volume",
        "setting_updated": "✅ Setting updated: {name} = {val}",
        "join_auto": "Auto-Join",
        "leave_auto": "Auto-Leave",
        "others_access": "Others access",
        "status_msg_on": "🔔 Live status enabled in this channel.",
        "status_msg_off": "🔕 Live status disabled.",
        "vol_up": "Vol +",
        "vol_down": "Vol -",
        "commands_toggle": "Owner only mode",
        "no_permission_commands": "❌ Commands are temporarily disabled by the owner.",
    },
}


def _resolve_lang(lang: Union[str, discord.Locale, None]) -> str:
    if lang is None:
        return DEFAULT_LOCALE
    code = str(lang).lower()
    return "ru" if code.startswith("ru") else "default"


def get_text(key: str, lang: Union[str, discord.Locale, None] = None) -> str:
    """Return localized string for *key*."""
    bucket = _resolve_lang(lang)
    table = _TRANSLATIONS[bucket]
    return table.get(key, _TRANSLATIONS["default"][key])


def load_settings() -> None:
    """Load persisted bot settings from JSON (thread-safe)."""
    global _bot_settings
    with _settings_lock:
        merged = dict(DEFAULT_SETTINGS)
        if SETTINGS_FILE.is_file():
            try:
                raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    merged.update(raw)
            except (OSError, json.JSONDecodeError) as exc:
                print(f"Error loading settings: {exc}")
        _bot_settings = merged


def save_settings() -> None:
    """Persist current bot settings to JSON (thread-safe)."""
    with _settings_lock:
        try:
            # BUG FIX: раньше тут был вызов не-существующей SETTINGS_DIR
            # (был объявлен только DATA_DIR) — save_settings() падал бы
            # с NameError при первом же сохранении.
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            SETTINGS_FILE.write_text(
                json.dumps(_bot_settings, indent=4, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            print(f"Error saving settings: {exc}")


def get_settings() -> Mapping[str, Any]:
    """Return a read-only snapshot of settings."""
    with _settings_lock:
        return dict(_bot_settings)


def get_setting(key: str, default: Any = None) -> Any:
    with _settings_lock:
        return _bot_settings.get(key, default)


def update_settings(updates: Mapping[str, Any]) -> None:
    with _settings_lock:
        _bot_settings.update(updates)


def mutate_setting(key: str, value: Any) -> None:
    with _settings_lock:
        _bot_settings[key] = value


def toggle_setting(key: str) -> bool:
    with _settings_lock:
        new_val = not bool(_bot_settings.get(key, False))
        _bot_settings[key] = new_val
        return new_val


# Load on import so modules see persisted values immediately.
load_settings()
