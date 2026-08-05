from __future__ import annotations

from typing import Any, Union

import discord
from discord.ext import commands

from bot.config import DEFAULT_LOCALE, DISCORD_BOT_OWNER_ID, get_setting, get_text

_FALLBACK_LOCALE: discord.Locale = (
    discord.Locale.russian if DEFAULT_LOCALE == "ru" else discord.Locale.american_english
)


class PermissionService:

    def __init__(self, bot: Any) -> None:
        self.bot = bot

    async def is_allowed(
        self, obj: Union[discord.Interaction, commands.Context[Any]]
    ) -> bool:
        is_interaction = isinstance(obj, discord.Interaction)
        guild = obj.guild
        if guild is None:
            return False

        owner = guild.get_member(DISCORD_BOT_OWNER_ID)
        user = obj.user if is_interaction else obj.author
        locale = obj.locale if is_interaction else _FALLBACK_LOCALE

        async def respond(text: str, *, ephemeral: bool = False) -> None:
            if is_interaction:
                if obj.response.is_done():
                    await obj.followup.send(text, ephemeral=ephemeral)
                else:
                    await obj.response.send_message(text, ephemeral=ephemeral)
            else:
                await obj.send(text)

        if user.id != DISCORD_BOT_OWNER_ID and get_setting(
            "only_owner_mode", False
        ):
            await respond(
                get_text("no_permission_commands", locale), ephemeral=True
            )
            return False

        if not owner or not owner.voice:
            await respond(get_text("owner_not_in_vc", locale), ephemeral=True)
            return False

        if not user.voice or user.voice.channel != owner.voice.channel:
            if (
                not get_setting("allow_others_vc")
                and user.id != DISCORD_BOT_OWNER_ID
            ):
                await respond(get_text("join_same_vc", locale), ephemeral=True)
                return False

        return True