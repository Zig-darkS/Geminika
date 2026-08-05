from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from bot.bot import MusicBot


def register_settings_commands(bot: MusicBot) -> None:
    @bot.tree.command(name="toggle_join", description="Auto-join VC (Owner)")
    async def toggle_join_cmd(interaction: discord.Interaction) -> None:
        await bot.execute_toggle(interaction, "auto_join", "join_auto")

    @bot.tree.command(name="toggle_leave", description="Auto-leave VC (Owner)")
    async def toggle_leave_cmd(interaction: discord.Interaction) -> None:
        await bot.execute_toggle(interaction, "auto_leave", "leave_auto")

    @bot.tree.command(name="toggle_others", description="Allow others in VC (Owner)")
    async def toggle_others_cmd(interaction: discord.Interaction) -> None:
        await bot.execute_toggle(interaction, "allow_others_vc", "others_access")

    @bot.tree.command(name="toggle_commands", description="Owner-only commands (Owner)")
    async def toggle_commands_cmd(interaction: discord.Interaction) -> None:
        await bot.execute_toggle_commands(interaction)

    @bot.command(name="toggle_join")
    async def toggle_join_p(ctx: commands.Context[Any]) -> None:
        await bot.execute_toggle(ctx, "auto_join", "join_auto")

    @bot.command(name="toggle_leave")
    async def toggle_leave_p(ctx: commands.Context[Any]) -> None:
        await bot.execute_toggle(ctx, "auto_leave", "leave_auto")

    @bot.command(name="toggle_others")
    async def toggle_others_p(ctx: commands.Context[Any]) -> None:
        await bot.execute_toggle(ctx, "allow_others_vc", "others_access")

    @bot.command(name="toggle_commands")
    async def toggle_commands_p(ctx: commands.Context[Any]) -> None:
        await bot.execute_toggle_commands(ctx)