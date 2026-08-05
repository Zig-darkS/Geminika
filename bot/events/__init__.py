from __future__ import annotations

from typing import TYPE_CHECKING

from bot.events.lifecycle import register_lifecycle_events
from bot.events.message import register_message_events
from bot.events.voice import register_voice_events

if TYPE_CHECKING:
    from bot.bot import MusicBot


def register_all_events(bot: MusicBot) -> None:
    register_lifecycle_events(bot)
    register_message_events(bot)
    register_voice_events(bot)