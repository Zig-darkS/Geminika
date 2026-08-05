from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord

from bot.config import VOLUME_STEP_DB, get_text

if TYPE_CHECKING:
    from bot.bot import MusicBot

class SpotifyControlView(discord.ui.View):
    """Persistent view — each button needs a stable custom_id for add_view()."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @staticmethod
    def _bot(interaction: discord.Interaction) -> MusicBot:
        client = interaction.client
        if client.__class__.__name__ != "MusicBot":
            raise TypeError("SpotifyControlView requires MusicBot client")
        return client

    @discord.ui.button(
        emoji="⏮️",
        style=discord.ButtonStyle.gray,
        custom_id="xd_spotify:prev",
    )
    async def prev_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._bot(interaction).spotify_service.previous(interaction)

    @discord.ui.button(
        emoji="⏯️",
        style=discord.ButtonStyle.blurple,
        custom_id="xd_spotify:pause",
    )
    async def pause_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._bot(interaction).spotify_service.pause(interaction)

    @discord.ui.button(
        emoji="⏭️",
        style=discord.ButtonStyle.gray,
        custom_id="xd_spotify:skip",
    )
    async def skip_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._bot(interaction).spotify_service.skip(interaction)

    @discord.ui.button(
        emoji="➕",
        style=discord.ButtonStyle.green,
        custom_id="xd_spotify:vol_up",
    )
    async def vol_up_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._bot(interaction).execute_vol(interaction, "add", VOLUME_STEP_DB)

    @discord.ui.button(
        emoji="➖",
        style=discord.ButtonStyle.red,
        custom_id="xd_spotify:vol_down",
    )
    async def vol_down_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._bot(interaction).execute_vol(interaction, "rem", VOLUME_STEP_DB)

    @discord.ui.button(
        emoji="🔇",
        style=discord.ButtonStyle.gray,
        custom_id="xd_spotify:mute",
    )
    async def mute_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        bot = self._bot(interaction)
        if await bot.permissions.is_allowed(interaction):
            muted = await asyncio.to_thread(bot.vm.toggle_mute)
            await bot.presence.update_status_data(muted=muted)
            msg = get_text("muted" if muted else "unmuted", interaction.locale)
            await interaction.response.send_message(msg, ephemeral=True)