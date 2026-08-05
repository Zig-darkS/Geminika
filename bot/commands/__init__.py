from __future__ import annotations

from typing import TYPE_CHECKING

from bot.commands.music import register_music_commands
from bot.commands.settings import register_settings_commands
from bot.commands.status import register_status_commands
from bot.commands.voice import register_voice_commands
from bot.commands.volume import register_volume_commands

if TYPE_CHECKING:
    from bot.bot import MusicBot


def register_all_commands(bot: MusicBot) -> None:
    register_music_commands(bot)
    register_volume_commands(bot)
    register_voice_commands(bot)
    register_settings_commands(bot)
    register_status_commands(bot)