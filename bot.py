# Deprecated monolith — use: python main.py
# Modules: config, voicemeeter_client, spotify_client, web_server, bot_instance, main
import discord
from discord import app_commands
from discord.ext import commands, tasks
import win32gui
import win32process
import ctypes
import asyncio
import atexit
import psutil
import os
import json
import time

# === НАСТРОЙКИ ===
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
DISCORD_BOT_OWNER_ID = int(os.getenv('DISCORD_BOT_OWNER_ID', 0))

SETTINGS_DIR = os.path.join(os.path.expanduser("~"), "Documents", "DiscordBot", "xd_bot")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "BotSettings.json")

# Important: Change this to match your exact Voicemeeter Output device name in Windows
VM_OUTPUT_DEVICE = "Voicemeeter Out B2 (VB-Audio Voicemeeter VAIO)"

# Multimedia control constants
WM_APPCOMMAND = 0x0319
MEDIA_NEXT = 0xB0000
MEDIA_PLAY_PAUSE = 0xE0000
MEDIA_PREV = 0xC0000

# Global state for tracking presence
last_track_name = None
track_start_time = None

RADIO_TASK = None # Track the radio stream

# Voicemeeter DLL setup
VM_DLL_PATH = r"C:\Program Files (x86)\VB\Voicemeeter\VoicemeeterRemote64.dll"
try:
    vm_dll = ctypes.windll.LoadLibrary(VM_DLL_PATH)
    vm_dll.VBVMR_Login()
except Exception as e:
    print(f"Voicemeeter DLL error: {e}")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Persistence Logic ---
bot_settings = {
    "volume_ceiling": -4.0,
    "auto_join": True,
    "auto_leave": True,
    "allow_others_vc": False,
    "status_msg_id": None,
    "status_channel_id": None,
    "status_enabled": False,
    "only_owner_mode": False
}

def load_settings():
    global bot_settings
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                bot_settings.update(json.load(f))
        except Exception as e:
            print(f"Error loading settings: {e}")

def save_settings():
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(bot_settings, f, indent=4)
    except Exception as e:
        print(f"Error saving settings: {e}")

# Initialize settings on script start
load_settings()

def get_text(locale: discord.Locale, key: str) -> str:
    """Localization helper."""
    translations = {
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
            "no_permission_commands": "❌ Команды временно отключены владельцем."
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
            "no_permission_commands": "❌ Commands are temporarily disabled by the owner."
        }
    }
    lang = "ru" if str(locale).startswith("ru") else "default"
    return translations[lang].get(key, translations["default"][key])

def send_spotify_command(command_code):
    """Mimics AHK 'ahk_exe Spotify.exe' logic."""
    target_hwnd = [None]

    def callback(hwnd, _):
        # Find main window by class or title related to Spotify process
        if win32gui.IsWindowVisible(hwnd):
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                proc = psutil.Process(pid)
                if proc.name().lower() == "spotify.exe":
                    title = win32gui.GetWindowText(hwnd)
                    # Spotify main window usually has a title or specific class
                    if title or win32gui.GetClassName(hwnd) == "Chrome_WidgetWin_0":
                        target_hwnd[0] = hwnd
                        return False # Stop enumeration
            except:
                pass
        return True

    # Fast path: hidden listener window
    hwnd = win32gui.FindWindow("SpotifyMainWindow", None)
    if not hwnd:
        try:
            win32gui.EnumWindows(callback, None)
        except Exception:
            # EnumWindows raises an error if callback returns False (which we do to stop early)
            pass
        hwnd = target_hwnd[0]

    if hwnd:
        win32gui.PostMessage(hwnd, WM_APPCOMMAND, 0, command_code)
        return True
    return False

def get_spotify_track_info():
    """Extract current track name or status from Spotify window."""
    target_info = {"title": "Idle", "active": False}
    
    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                proc = psutil.Process(pid)
                if proc.name().lower() == "spotify.exe":
                    title = win32gui.GetWindowText(hwnd)
                    # Check against common idle titles
                    if title and title not in ["Spotify", "Spotify Free", "Музыка без помех"]:
                        target_info["title"] = title
                        target_info["active"] = True
                        return False
            except: pass
        return True

    hwnd = win32gui.FindWindow("SpotifyMainWindow", None)
    if not hwnd:
        try: win32gui.EnumWindows(callback, None)
        except: pass
    return target_info

def vm_set_volume(value):
    """Set Voicemeeter Strip[7] Gain."""
    new_vol = max(-60.0, min(12.0, float(value)))
    vm_dll.VBVMR_SetParameterFloat(b"Strip[7].Gain", ctypes.c_float(new_vol))
    return new_vol

def vm_get_volume():
    """Read current Gain from Strip[7]."""
    vm_dll.VBVMR_IsParametersDirty()
    val = ctypes.c_float()
    vm_dll.VBVMR_GetParameterFloat(b"Strip[7].Gain", ctypes.byref(val))
    return val.value

def vm_get_mute():
    """Read current Mute status from Strip[7]."""
    vm_dll.VBVMR_IsParametersDirty()
    val = ctypes.c_float()
    vm_dll.VBVMR_GetParameterFloat(b"Strip[7].Mute", ctypes.byref(val))
    return val.value > 0.5

def vm_set_mute(state: bool):
    """Set Mute status for Strip[7]."""
    # Voicemeeter Mute uses 1.0 for True, 0.0 for False
    vm_dll.VBVMR_IsParametersDirty() # Refresh before action
    val = float(1.0 if state else 0.0)
    vm_dll.VBVMR_SetParameterFloat(b"Strip[7].Mute", ctypes.c_float(val))
    return state

class SpotifyControlView(discord.ui.View):
    """Interactive buttons for Spotify control."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.gray)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await execute_prev(interaction)

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.blurple)
    async def pause_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await execute_pause(interaction)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.gray)
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await execute_skip(interaction)

    @discord.ui.button(emoji="➕", style=discord.ButtonStyle.green)
    async def vol_up_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await execute_vol(interaction, "add", 2.0)

    @discord.ui.button(emoji="➖", style=discord.ButtonStyle.red)
    async def vol_down_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await execute_vol(interaction, "rem", 2.0)

    @discord.ui.button(emoji="🔇", style=discord.ButtonStyle.gray)
    async def mute_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await is_allowed(interaction):
            new_state = not vm_get_mute()
            vm_set_mute(new_state)
            msg = get_text(interaction.locale, "muted" if new_state else "unmuted")
            await interaction.response.send_message(msg, ephemeral=True)

def create_now_embed(locale, info, vol, muted):
    title = info['title'] if info['active'] else get_text(locale, "nothing_playing")
    mute_icon = "🔇" if muted else "🔊"
    bar_size = 10
    filled = int(((vol + 60) / 72) * bar_size)
    bar = "▰" * filled + "▱" * (bar_size - filled)
    embed = discord.Embed(title=f"{mute_icon} {get_text(locale, 'now_playing')}", description=f"**{title}**", color=0x1DB954)
    embed.add_field(name=get_text(locale, "volume_bar"), value=f"`{bar}` {round(vol, 1)} dB", inline=False)
    return embed

async def vm_fade_volume(target_v):
    """Smoothly transition volume to target value."""
    current = vm_get_volume()
    # Determine number of steps (0.1dB per step is smooth)
    steps = int(abs(target_v - current) / 0.5)
    if steps < 1: steps = 1
    if steps > 20: steps = 20 # Cap to prevent long freezes
    
    delta = (target_v - current) / steps
    for _ in range(steps):
        current += delta
        vm_set_volume(current)
        await asyncio.sleep(0.05)
    vm_set_volume(target_v) # Ensure final value is exact

@atexit.register
def on_exit():
    """Logout from Voicemeeter on script exit."""
    save_settings()
    vm_dll.VBVMR_Logout()

async def is_allowed(obj):
    """Check voice channel constraints for both Interaction and Context."""
    is_interaction = isinstance(obj, discord.Interaction)
    guild = obj.guild
    owner = guild.get_member(DISCORD_BOT_OWNER_ID)
    user = obj.user if is_interaction else obj.author
    locale = obj.locale if is_interaction else discord.Locale.russian # Default for prefix
    
    # Check if only owner mode is enabled
    if user.id != DISCORD_BOT_OWNER_ID and bot_settings.get("only_owner_mode", False):
        await respond(get_text(locale, "no_permission_commands"), ephemeral=True)
        return False

    # Helper to respond to either interaction or context
    async def respond(text, ephemeral=False):
        if is_interaction:
            await obj.response.send_message(text, ephemeral=ephemeral)
        else:
            await obj.send(text)

    if not owner or not owner.voice:
        await respond(get_text(locale, "owner_not_in_vc"), ephemeral=True)
        return False
        
    # If owner is not in the requester's channel
    if not user.voice or user.voice.channel != owner.voice.channel:
        # Check if others are allowed to control/call bot when owner is not around
        if not bot_settings["allow_others_vc"] and user.id != DISCORD_BOT_OWNER_ID:
            await respond(get_text(locale, "join_same_vc"), ephemeral=True)
            return False
            
    return True

# --- Logic Wrappers ---
async def execute_pause(target):
    if await is_allowed(target):
        locale = target.locale if isinstance(target, discord.Interaction) else discord.Locale.russian
        if send_spotify_command(MEDIA_PLAY_PAUSE):
            msg = get_text(locale, "paused")
        else:
            msg = get_text(locale, "not_found")
        
        if isinstance(target, discord.Interaction):
            await target.response.send_message(msg)
        else:
            await target.send(msg)

async def execute_skip(target):
    if await is_allowed(target):
        locale = target.locale if isinstance(target, discord.Interaction) else discord.Locale.russian
        msg = get_text(locale, "skipped") if send_spotify_command(MEDIA_NEXT) else get_text(locale, "not_found")
        if isinstance(target, discord.Interaction):
            await target.response.send_message(msg)
        else:
            await target.send(msg)

async def execute_prev(target):
    if await is_allowed(target):
        locale = target.locale if isinstance(target, discord.Interaction) else discord.Locale.russian
        msg = get_text(locale, "prev") if send_spotify_command(MEDIA_PREV) else get_text(locale, "not_found")
        if isinstance(target, discord.Interaction):
            await target.response.send_message(msg)
        else:
            await target.send(msg)

async def execute_prev2(target):
    if await is_allowed(target):
        locale = target.locale if isinstance(target, discord.Interaction) else discord.Locale.russian
        success = send_spotify_command(MEDIA_PREV)
        if success:
            await asyncio.sleep(0.2) # Non-blocking delay for Spotify
            send_spotify_command(MEDIA_PREV)
            msg = get_text(locale, "prev2")
        else:
            msg = get_text(locale, "not_found")
        
        if isinstance(target, discord.Interaction):
            await target.response.send_message(msg)
        else:
            await target.send(msg)

async def execute_vol(target, mode, value):
    """Handle volume commands: set, add, rem."""
    if await is_allowed(target):
        is_interaction = isinstance(target, discord.Interaction)
        user = target.user if is_interaction else target.author
        locale = target.locale if is_interaction else discord.Locale.russian
        current = vm_get_volume()
        
        if mode == "set": new_v = value
        elif mode == "add": new_v = current + value
        else: new_v = current - value
        
        # Limit logic for non-owners
        if user.id != DISCORD_BOT_OWNER_ID:
            new_v = min(new_v, max(current, bot_settings["volume_ceiling"]))

        # Use fade for smooth transition
        await vm_fade_volume(new_v)
        # Fix: Show the target volume (new_v) instead of potentially stale current volume
        await update_status_data()
        msg = get_text(locale, "vol_update").format(v=round(new_v, 1))
        
        if isinstance(target, discord.Interaction):
            await target.response.send_message(msg)
        else:
            await target.send(msg)

async def execute_vlimit(target, db: float):
    """Change the volume ceiling (Owner only)."""
    is_interaction = isinstance(target, discord.Interaction)
    user = target.user if is_interaction else target.author
    locale = target.locale if is_interaction else discord.Locale.russian
    
    if user.id != DISCORD_BOT_OWNER_ID:
        msg = get_text(locale, "no_permission")
    else:
        bot_settings["volume_ceiling"] = max(-60.0, min(12.0, db))
        save_settings()
        msg = get_text(locale, "vlimit_set").format(v=bot_settings["volume_ceiling"])

    if is_interaction:
        await target.response.send_message(msg)
    else:
        await target.send(msg)

async def execute_toggle(target, setting_key, name_key):
    """Toggle owner-only settings."""
    is_interaction = isinstance(target, discord.Interaction)
    user = target.user if is_interaction else target.author
    locale = target.locale if is_interaction else discord.Locale.russian

    if user.id != DISCORD_BOT_OWNER_ID:
        msg = get_text(locale, "no_permission")
    else:
        bot_settings[setting_key] = not bot_settings[setting_key]
        save_settings()
        msg = get_text(locale, "setting_updated").format(name=get_text(locale, name_key), val=bot_settings[setting_key])

    if is_interaction:
        await target.response.send_message(msg)
    else:
        await target.send(msg)

async def execute_toggle_commands(target):
    """Toggle global command access (Owner only)."""
    is_interaction = isinstance(target, discord.Interaction)
    user = target.user if is_interaction else target.author
    locale = target.locale if is_interaction else discord.Locale.russian

    if user.id != DISCORD_BOT_OWNER_ID:
        msg = get_text(locale, "no_permission")
    else:
        bot_settings["only_owner_mode"] = not bot_settings.get("only_owner_mode", False)
        save_settings()
        msg = get_text(locale, "setting_updated").format(name=get_text(locale, "commands_toggle"), val=bot_settings["only_owner_mode"])

    if is_interaction:
        await target.response.send_message(msg)
    else:
        await target.send(msg)

async def execute_now(target):
    """Show current track and volume status."""
    locale = target.locale if isinstance(target, discord.Interaction) else discord.Locale.russian
    info = get_spotify_track_info()
    vol = vm_get_volume()
    muted = vm_get_mute()
    
    embed = create_now_embed(locale, info, vol, muted)
    if isinstance(target, discord.Interaction):
        await target.response.send_message(embed=embed, view=SpotifyControlView())
    else:
        await target.send(embed=embed, view=SpotifyControlView())

async def execute_toggle_now(target):
    """Toggle persistent updating status message."""
    is_interaction = isinstance(target, discord.Interaction)
    user = target.user if is_interaction else target.author
    locale = target.locale if is_interaction else discord.Locale.russian

    if user.id != DISCORD_BOT_OWNER_ID:
        await (target.response.send_message(get_text(locale, "no_permission")) if is_interaction else target.send(get_text(locale, "no_permission")))
        return

    bot_settings["status_enabled"] = not bot_settings["status_enabled"]
    if bot_settings["status_enabled"]:
        info = get_spotify_track_info()
        embed = create_now_embed(locale, info, vm_get_volume(), vm_get_mute())
        msg = await (target.channel.send(embed=embed, view=SpotifyControlView()))
        bot_settings["status_msg_id"] = msg.id
        bot_settings["status_channel_id"] = msg.channel.id
        res_msg = get_text(locale, "status_msg_on")
    else:
        bot_settings["status_msg_id"] = None
        res_msg = get_text(locale, "status_msg_off")
    
    await update_status_data()
    save_settings()
    if is_interaction:
        await target.response.send_message(res_msg)
    else:
        await target.send(res_msg)

async def start_radio(guild):
    """Internal helper to start radio stream with low latency."""
    vc = guild.voice_client
    if not vc or not vc.is_connected():
        return

    if vc.is_playing():
        vc.stop()

    # Low latency FFmpeg flags:
    # -audio_buffer_size: minimal buffer for dshow
    # -threads 1: prevent sync issues
    # -preset ultrafast -tune zerolatency: minimal encoding delay
    before_args = f"-f dshow -rtbufsize 100M -audio_buffer_size 50"
    after_args = f"-vn -ac 2 -ar 48000 -threads 1 -preset ultrafast -tune zerolatency"
    
    try:
        source = discord.FFmpegPCMAudio(f"audio={VM_OUTPUT_DEVICE}", before_options=before_args, options=after_args)
        vc.play(source)
    except Exception as e:
        print(f"Streaming error: {e}")

async def update_status_data():
    """Core logic to refresh Discord Presence and the persistent status message."""
    global last_track_name, track_start_time
    try:
        if not vm_dll:
            return
            
        vm_dll.VBVMR_IsParametersDirty()
        vol = vm_get_volume()
        muted = vm_get_mute()
        info = get_spotify_track_info()
        
        track_name = info['title'] if info['active'] else get_text(discord.Locale.russian, "nothing_playing")
        
        # Update timestamp only if track changed
        if track_name != last_track_name:
            last_track_name = track_name
            track_start_time = int(time.time())

        mute_icon = "🔇" if muted else "🔊"
        
        # Presence info
        vc_info = "Not in VC"
        guild_info = "Idle"
        if bot.voice_clients:
            vc = bot.voice_clients[0]
            guild_info = f"Server: {vc.guild.name}"
            vc_info = f"Room: {vc.channel.name}"

        # Update Presence: Icon VolumedB | Track
        status_name = f"{mute_icon} {round(vol, 1)}dB | {track_name}"

        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name=status_name,
            details=f"{guild_info}",
            state=vc_info,
            timestamps={"start": track_start_time}
        )
        await bot.change_presence(activity=activity)

        # Update persistent message if enabled
        if bot_settings["status_enabled"] and bot_settings["status_msg_id"]:
            channel = bot.get_channel(bot_settings["status_channel_id"])
            if channel:
                try:
                    msg = await channel.fetch_message(bot_settings["status_msg_id"])
                    await msg.edit(embed=create_now_embed(discord.Locale.russian, info, vol, muted), view=SpotifyControlView())
                except: pass
    except Exception as e:
        print(f"Presence error: {e}")

@tasks.loop(seconds=15) # Optimized sync
async def update_presence():
    """Background task to update bot's activity status."""
    await update_status_data()

@bot.event
async def on_ready():
    await bot.tree.sync() # Sync slash commands
    update_presence.start() # Start status loop
    print(f'Logged in as {bot.user.name}')

@bot.event
async def on_voice_state_update(member, before, after):
    """Auto-join logic when owner enters a channel."""
    if member.id != DISCORD_BOT_OWNER_ID:
        return

    # Owner left channel
    if before.channel and after.channel is None and bot_settings["auto_leave"]:
        vc = member.guild.voice_client
        if vc:
            await vc.disconnect()
        return

    # Owner joined a new channel
    if after.channel and before.channel != after.channel and bot_settings["auto_join"]:
        vc = member.guild.voice_client
        if vc:
            await vc.move_to(after.channel)
        else:
            await after.channel.connect(self_deaf=True)
        
        # Delay slightly to ensure connection is stable
        await asyncio.sleep(1)
        await start_radio(member.guild)

# --- Slash Commands ---
@bot.tree.command(name="pause", description="Pause or Resume Spotify")
async def pause(interaction: discord.Interaction):
    await execute_pause(interaction)

@bot.tree.command(name="skip", description="Next track")
async def skip(interaction: discord.Interaction):
    await execute_skip(interaction)

@bot.tree.command(name="prev", description="Previous track")
async def prev(interaction: discord.Interaction):
    await execute_prev(interaction)

@bot.tree.command(name="prev2", description="Back 2 tracks")
async def prev2(interaction: discord.Interaction):
    await execute_prev2(interaction)

@bot.tree.command(name="vset", description="Set volume in dB (-60 to 12)")
async def vset(interaction: discord.Interaction, db: float):
    await execute_vol(interaction, "set", db)

@bot.tree.command(name="vadd", description="Increase volume by dB")
async def vadd(interaction: discord.Interaction, db: float):
    await execute_vol(interaction, "add", db)

@bot.tree.command(name="vrem", description="Decrease volume by dB")
async def vrem(interaction: discord.Interaction, db: float):
    await execute_vol(interaction, "rem", db)

@bot.tree.command(name="vlimit", description="Set volume ceiling for users (Owner only)")
async def vlimit(interaction: discord.Interaction, db: float):
    await execute_vlimit(interaction, db)

@bot.tree.command(name="now", description="Show current track and volume info")
async def now_slash(interaction: discord.Interaction):
    await execute_now(interaction)

@bot.tree.command(name="toggle_now", description="Post and auto-update status message in this channel (Owner only)")
async def toggle_now_slash(interaction: discord.Interaction):
    await execute_toggle_now(interaction)

@bot.tree.command(name="toggle_join", description="Toggle auto-join when owner enters VC (Owner only)")
async def toggle_join_slash(interaction: discord.Interaction):
    await execute_toggle(interaction, "auto_join", "join_auto")

@bot.tree.command(name="toggle_leave", description="Toggle auto-leave when owner leaves VC (Owner only)")
async def toggle_leave_slash(interaction: discord.Interaction):
    await execute_toggle(interaction, "auto_leave", "leave_auto")

@bot.tree.command(name="toggle_others", description="Allow others to control bot when owner is absent (Owner only)")
async def toggle_others_slash(interaction: discord.Interaction):
    await execute_toggle(interaction, "allow_others_vc", "others_access")

@bot.tree.command(name="toggle_commands", description="Disable all commands for non-owners (Owner only)")
async def toggle_commands_slash(interaction: discord.Interaction):
    await execute_toggle_commands(interaction)

@bot.tree.command(name="mute", description="Mute/Unmute Voicemeeter Strip[7]")
async def mute(interaction: discord.Interaction):
    if await is_allowed(interaction):
        new_state = not vm_get_mute()
        vm_set_mute(new_state)
        await update_status_data()
        msg = get_text(interaction.locale, "muted" if new_state else "unmuted")
        await interaction.response.send_message(msg)

# --- Prefix Commands (!) ---
@bot.command(name="pause")
async def pause_prefix(ctx):
    await execute_pause(ctx)

@bot.command(name="skip")
async def skip_prefix(ctx):
    await execute_skip(ctx)

@bot.command(name="prev")
async def prev_prefix(ctx):
    await execute_prev(ctx)

@bot.command(name="prev2")
async def prev2_prefix(ctx):
    await execute_prev2(ctx)

@bot.command(name="vset")
async def vset_prefix(ctx, db: float):
    await execute_vol(ctx, "set", db)

@bot.command(name="vadd")
async def vadd_prefix(ctx, db: float):
    await execute_vol(ctx, "add", db)

@bot.command(name="vrem")
async def vrem_prefix(ctx, db: float):
    await execute_vol(ctx, "rem", db)

@bot.command(name="vlimit")
async def vlimit_prefix(ctx, db: float):
    await execute_vlimit(ctx, db)

@bot.command(name="now")
async def now_prefix(ctx):
    await execute_now(ctx)

@bot.command(name="toggle_now")
async def toggle_now_p(ctx):
    await execute_toggle_now(ctx)

@bot.command(name="toggle_join")
async def toggle_join_p(ctx):
    await execute_toggle(ctx, "auto_join", "join_auto")

@bot.command(name="toggle_leave")
async def toggle_leave_p(ctx):
    await execute_toggle(ctx, "auto_leave", "leave_auto")

@bot.command(name="toggle_others")
async def toggle_others_p(ctx):
    await execute_toggle(ctx, "allow_others_vc", "others_access")

@bot.command(name="toggle_commands")
async def toggle_commands_p(ctx):
    await execute_toggle_commands(ctx)

@bot.command(name="mute")
async def mute_prefix(ctx):
    if await is_allowed(ctx):
        new_state = not vm_get_mute()
        vm_set_mute(new_state)
        await update_status_data()
        await ctx.send(get_text(discord.Locale.russian, "muted" if new_state else "unmuted"))

@bot.tree.command(name="join", description="Join and start radio streaming")
async def join(interaction: discord.Interaction):
    if await is_allowed(interaction):
        channel = interaction.user.voice.channel
        vc = interaction.guild.voice_client
        
        if vc:
            await vc.move_to(channel)
        else:
            vc = await channel.connect(self_deaf=True)
        
        await start_radio(interaction.guild)
        await interaction.response.send_message(get_text(interaction.locale, "joined"))

@bot.tree.command(name="leave", description="Leave voice channel")
async def leave(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message(get_text(interaction.locale, "left"))
    else:
        await interaction.response.send_message("I'm not in a voice channel.", ephemeral=True)

bot.run(DISCORD_BOT_TOKEN)