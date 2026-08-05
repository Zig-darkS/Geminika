from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Union

import discord
from discord.ext import commands

from bot.config import DEFAULT_LOCALE, get_text

if TYPE_CHECKING:
    from bot.bot import MusicBot

_FALLBACK_LOCALE: discord.Locale = (
    discord.Locale.russian if DEFAULT_LOCALE == "ru" else discord.Locale.american_english
)


class SpotifyService:

    def __init__(self, bot: MusicBot) -> None:
        self.bot = bot

    async def pause(
        self, target: Union[discord.Interaction, commands.Context[Any]]
    ) -> None:
        if not await self.bot.permissions.is_allowed(target):
            return
        locale = (
            target.locale
            if isinstance(target, discord.Interaction)
            else _FALLBACK_LOCALE
        )
        ok = await asyncio.to_thread(self.bot.spotify.play_pause)
        msg = get_text("paused" if ok else "not_found", locale)
        await self.bot.presence.update_status_data()
        if isinstance(target, discord.Interaction):
            await target.response.send_message(msg)
        else:
            await target.send(msg)

    async def skip(
        self, target: Union[discord.Interaction, commands.Context[Any]]
    ) -> None:
        if not await self.bot.permissions.is_allowed(target):
            return
        locale = (
            target.locale
            if isinstance(target, discord.Interaction)
            else _FALLBACK_LOCALE
        )
        ok = await asyncio.to_thread(self.bot.spotify.next_track)
        msg = get_text("skipped" if ok else "not_found", locale)
        await self.bot.presence.update_status_data()
        if isinstance(target, discord.Interaction):
            await target.response.send_message(msg)
        else:
            await target.send(msg)

    async def previous(
        self, target: Union[discord.Interaction, commands.Context[Any]]
    ) -> None:
        if not await self.bot.permissions.is_allowed(target):
            return
        locale = (
            target.locale
            if isinstance(target, discord.Interaction)
            else _FALLBACK_LOCALE
        )
        ok = await asyncio.to_thread(self.bot.spotify.previous_track)
        msg = get_text("prev" if ok else "not_found", locale)
        await self.bot.presence.update_status_data()
        if isinstance(target, discord.Interaction):
            await target.response.send_message(msg)
        else:
            await target.send(msg)

    async def previous2(
        self, target: Union[discord.Interaction, commands.Context[Any]]
    ) -> None:
        if not await self.bot.permissions.is_allowed(target):
            return
        locale = (
            target.locale
            if isinstance(target, discord.Interaction)
            else _FALLBACK_LOCALE
        )
        ok = await asyncio.to_thread(self.bot.spotify.previous_track_twice)
        msg = get_text("prev2" if ok else "not_found", locale)
        await self.bot.presence.update_status_data()
        if isinstance(target, discord.Interaction):
            await target.response.send_message(msg)
        else:
            await target.send(msg)