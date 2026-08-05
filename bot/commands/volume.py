from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands

from bot.config import DEFAULT_LOCALE, VOLUME_STEP_DB, get_text

if TYPE_CHECKING:
    from bot.bot import MusicBot

_FALLBACK_LOCALE: discord.Locale = (
    discord.Locale.russian if DEFAULT_LOCALE == "ru" else discord.Locale.american_english
)


def register_volume_commands(bot: MusicBot) -> None:
    @bot.tree.command(name="vset", description="Set volume in dB (-60 to 12)")
    async def vset_cmd(interaction: discord.Interaction, db: float) -> None:
        await bot.execute_vol(interaction, "set", db)

    @bot.tree.command(name="vadd", description="Increase volume by dB")
    async def vadd_cmd(interaction: discord.Interaction, db: float = VOLUME_STEP_DB) -> None:
        await bot.execute_vol(interaction, "add", db)

    @bot.tree.command(name="vrem", description="Decrease volume by dB")
    async def vrem_cmd(interaction: discord.Interaction, db: float = VOLUME_STEP_DB) -> None:
        await bot.execute_vol(interaction, "rem", db)

    @bot.tree.command(name="vlimit", description="Volume ceiling (Owner)")
    async def vlimit_cmd(interaction: discord.Interaction, db: float) -> None:
        await bot.execute_vlimit(interaction, db)

    @bot.tree.command(name="mute", description="Mute/Unmute Strip[7]")
    async def mute_cmd(interaction: discord.Interaction) -> None:
        if await bot.permissions.is_allowed(interaction):
            muted = await bot.volume.toggle_mute()
            msg = get_text("muted" if muted else "unmuted", interaction.locale)
            await interaction.response.send_message(msg)

    @bot.command(name="vset")
    async def vset_p(ctx: commands.Context[Any], db: float) -> None:
        await bot.execute_vol(ctx, "set", db)

    @bot.command(name="vadd")
    async def vadd_p(ctx: commands.Context[Any], db: float = VOLUME_STEP_DB) -> None:
        await bot.execute_vol(ctx, "add", db)

    @bot.command(name="vrem")
    async def vrem_p(ctx: commands.Context[Any], db: float = VOLUME_STEP_DB) -> None:
        await bot.execute_vol(ctx, "rem", db)

    @bot.command(name="vlimit")
    async def vlimit_p(ctx: commands.Context[Any], db: float) -> None:
        await bot.execute_vlimit(ctx, db)

    @bot.command(name="mute")
    async def mute_p(ctx: commands.Context[Any]) -> None:
        if await bot.permissions.is_allowed(ctx):
            muted = await bot.volume.toggle_mute()
            await ctx.send(get_text("muted" if muted else "unmuted", _FALLBACK_LOCALE))