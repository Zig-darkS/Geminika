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

# --- AHK bridge auth (пусто = проверка выключена) ---
BRIDGE_TOKEN: Final[str] = os.environ.get("BRIDGE_TOKEN", "").strip()

# --- Voicemeeter ---
VM_DLL_PATH: Final[Path] = Path(
    r"C:\Program Files (x86)\VB\Voicemeeter\VoicemeeterRemote64.dll"
)
VM_STRIP_INDEX: Final[int] = 7

# --- Audio / streaming ---
VM_OUTPUT_DEVICE: Final[str] = os.environ.get(
    "VM_OUTPUT_DEVICE",
    "Voicemeeter Out B2 (VB-Audio Voicemeeter VAIO)",
)

# --- HTTP bridge (AHK -> Python) ---
WEB_HOST: Final[str] = "127.0.0.1"
WEB_PORT: Final[int] = 5000
WEB_BASE_URL: Final[str] = f"http://{WEB_HOST}:{WEB_PORT}"

# --- Multimedia (Win32) ---
WM_APPCOMMAND: Final[int] = 0x0319
MEDIA_NEXT: Final[int] = 0xB0000
MEDIA_PLAY_PAUSE: Final[int] = 0xE0000
MEDIA_PREV: Final[int] = 0xC0000

SPOTIFY_IDLE_TITLES: Final[frozenset[str]] = frozenset(
    {"Spotify", "Spotify Free", "Музыка без помех", ""}
)

# --- Default persisted settings ---
DEFAULT_SETTINGS: Final[dict[str, Any]] = {
    "volume_ceiling": -4.0,
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
        return "default"
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
            SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
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
