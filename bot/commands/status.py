from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from bot.bot import MusicBot


def register_status_commands(bot: MusicBot) -> None:
    @bot.tree.command(name="now", description="Current track and volume")
    async def now_cmd(interaction: discord.Interaction) -> None:
        await bot.execute_now(interaction)

    @bot.tree.command(name="toggle_now", description="Live status message (Owner)")
    async def toggle_now_cmd(interaction: discord.Interaction) -> None:
        await bot.execute_toggle_now(interaction)

    @bot.command(name="now")
    async def now_p(ctx: commands.Context[Any]) -> None:
        await bot.execute_now(ctx)

    @bot.command(name="toggle_now")
    async def toggle_now_p(ctx: commands.Context[Any]) -> None:
        await bot.execute_toggle_now(ctx)