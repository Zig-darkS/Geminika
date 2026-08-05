from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from bot.bot import MusicBot


def register_music_commands(bot: MusicBot) -> None:
    @bot.tree.command(name="pause", description="Pause or Resume Spotify")
    async def pause_cmd(interaction: discord.Interaction) -> None:
        await bot.spotify_service.pause(interaction)

    @bot.tree.command(name="skip", description="Next track")
    async def skip_cmd(interaction: discord.Interaction) -> None:
        await bot.spotify_service.skip(interaction)

    @bot.tree.command(name="prev", description="Previous track")
    async def prev_cmd(interaction: discord.Interaction) -> None:
        await bot.spotify_service.previous(interaction)

    @bot.tree.command(name="prev2", description="Back 2 tracks")
    async def prev2_cmd(interaction: discord.Interaction) -> None:
        await bot.spotify_service.previous2(interaction)

    @bot.command(name="pause")
    async def pause_p(ctx: commands.Context[Any]) -> None:
        await bot.spotify_service.pause(ctx)

    @bot.command(name="skip")
    async def skip_p(ctx: commands.Context[Any]) -> None:
        await bot.spotify_service.skip(ctx)

    @bot.command(name="prev")
    async def prev_p(ctx: commands.Context[Any]) -> None:
        await bot.spotify_service.previous(ctx)

    @bot.command(name="prev2")
    async def prev2_p(ctx: commands.Context[Any]) -> None:
        await bot.spotify_service.previous2(ctx)