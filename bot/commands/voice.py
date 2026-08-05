from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from bot.config import get_text

if TYPE_CHECKING:
    from bot.bot import MusicBot


def register_voice_commands(bot: MusicBot) -> None:
    @bot.tree.command(name="join", description="Join and start radio")
    async def join_cmd(interaction: discord.Interaction) -> None:
        if await bot.permissions.is_allowed(interaction):
            channel = interaction.user.voice.channel
            vc = interaction.guild.voice_client
            if vc:
                await vc.move_to(channel)
            else:
                await channel.connect(self_deaf=True)
            await bot.start_radio(interaction.guild)
            await interaction.response.send_message(
                get_text("joined", interaction.locale)
            )

    @bot.tree.command(name="leave", description="Leave voice channel")
    async def leave_cmd(interaction: discord.Interaction) -> None:
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
            await interaction.response.send_message(
                get_text("left", interaction.locale)
            )
        else:
            await interaction.response.send_message(
                "I'm not in a voice channel.", ephemeral=True
            )