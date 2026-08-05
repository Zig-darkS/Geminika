from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord

from bot.config import DISCORD_BOT_OWNER_ID, get_setting

if TYPE_CHECKING:
    from bot.bot import MusicBot


def register_voice_events(bot: MusicBot) -> None:
    @bot.event
    async def on_voice_state_update(
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.id != DISCORD_BOT_OWNER_ID:
            return
        if before.channel and after.channel is None and get_setting("auto_leave"):
            vc = member.guild.voice_client
            if vc:
                await vc.disconnect()
            return
        if (
            after.channel
            and before.channel != after.channel
            and get_setting("auto_join")
        ):
            vc = member.guild.voice_client
            if vc:
                await vc.move_to(after.channel)
            else:
                await after.channel.connect(self_deaf=True)
            await asyncio.sleep(1)
            await bot.start_radio(member.guild)