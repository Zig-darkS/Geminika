from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.bot import MusicBot


def register_lifecycle_events(bot: MusicBot) -> None:
    @bot.event
    async def on_ready() -> None:
        await bot.presence.start_task()
        for guild in bot.guilds:
            asyncio.create_task(bot.profile_tracker.snapshot_all_members(guild))
        print(f"Logged in as {bot.user} (Discord)")