from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from bot.bot import MusicBot


def register_message_events(bot: MusicBot) -> None:
    @bot.event
    async def on_message(message: discord.Message) -> None:
        if not message.author.bot:
            asyncio.create_task(
                bot.profile_tracker.record(
                    user=message.author,
                    guild_id=message.guild.id if message.guild else None,
                    reason="message_seen",
                )
            )
        await bot.process_commands(message)