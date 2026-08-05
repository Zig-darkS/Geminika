"""Discord bot: slash commands, views, radio stream, presence updates."""

from __future__ import annotations

import asyncio
from typing import Any, Literal, Union

import discord
from discord.ext import commands

from bot.config import (
    COMMAND_PREFIX,
    DEFAULT_LOCALE,
    DISCORD_BOT_OWNER_ID,
    DISCORD_BOT_TOKEN,
    FFMPEG_AFTER_ARGS,
    FFMPEG_BEFORE_ARGS,
    VM_MAX_DB,
    VM_MIN_DB,
    VM_OUTPUT_DEVICE,
    get_setting,
    get_text,
    mutate_setting,
    save_settings,
    toggle_setting,
    update_settings,
)
from bot.services.profile_tracker import ProfileTracker, install as install_profile_tracker
from bot.services.spotify_client import SpotifyClient
from bot.services.voicemeeter_client import VoicemeeterClient

from bot.commands import register_all_commands
from bot.events import register_all_events
from bot.models.live_status import LiveStatusState
from bot.services.embed_service import create_now_embed
from bot.services.permission_service import PermissionService
from bot.services.presence_service import PresenceService
from bot.services.spotify_service import SpotifyService
from bot.services.volume_service import VolumeService
from bot.views.spotify_control_view import SpotifyControlView

_FALLBACK_LOCALE: discord.Locale = (
    discord.Locale.russian if DEFAULT_LOCALE == "ru" else discord.Locale.american_english
)


class MusicBot(commands.Bot):
    def __init__(self, vm: VoicemeeterClient, spotify: SpotifyClient) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix=COMMAND_PREFIX, intents=intents)

        self.vm = vm
        self.spotify = spotify
        self.profile_tracker = ProfileTracker()

        # Services
        self.permissions = PermissionService(self)
        self.presence = PresenceService(self)
        self.volume = VolumeService(self)
        self.spotify_service = SpotifyService(self)

    def get_live_state(self) -> LiveStatusState:
        if not self.vm.is_connected:
            info = self.spotify.get_track_info()
            title = (
                info.title
                if info.active
                else get_text("nothing_playing", DEFAULT_LOCALE)
            )
            return LiveStatusState(0.0, False, title, info.active)
        state = self.vm.get_state()
        info = self.spotify.get_track_info()
        title = (
            info.title if info.active else get_text("nothing_playing", DEFAULT_LOCALE)
        )
        return LiveStatusState(
            state.volume_db, state.muted, title, info.active
        )

    async def start_radio(self, guild: discord.Guild) -> None:
        vc = guild.voice_client
        if not vc or not vc.is_connected():
            return
        if vc.is_playing():
            vc.stop()
        try:
            source = discord.FFmpegPCMAudio(
                f"audio={VM_OUTPUT_DEVICE}",
                before_options=FFMPEG_BEFORE_ARGS,
                options=FFMPEG_AFTER_ARGS,
            )
            vc.play(source)
        except Exception as exc:
            print(f"Streaming error: {exc}")

    async def execute_vol(
        self,
        target: Union[discord.Interaction, commands.Context[Any]],
        mode: Literal["set", "add", "rem"],
        value: float,
    ) -> None:
        if not await self.permissions.is_allowed(target):
            return
        is_interaction = isinstance(target, discord.Interaction)
        user = target.user if is_interaction else target.author
        locale = target.locale if is_interaction else _FALLBACK_LOCALE
        current = await asyncio.to_thread(self.vm.get_volume)
        if mode == "set":
            new_v = value
        elif mode == "add":
            new_v = current + value
        else:
            new_v = current - value

        if user.id != DISCORD_BOT_OWNER_ID:
            ceiling = float(get_setting("volume_ceiling", -4.0))
            new_v = min(new_v, max(current, ceiling))

        new_v = await self.volume.set_volume(new_v)
        msg = get_text("vol_update", locale).format(v=round(new_v, 1))
        if is_interaction:
            await target.response.send_message(msg)
        else:
            await target.send(msg)

    async def execute_vlimit(
        self,
        target: Union[discord.Interaction, commands.Context[Any]],
        db: float,
    ) -> None:
        is_interaction = isinstance(target, discord.Interaction)
        user = target.user if is_interaction else target.author
        locale = target.locale if is_interaction else _FALLBACK_LOCALE
        if user.id != DISCORD_BOT_OWNER_ID:
            msg = get_text("no_permission", locale)
        else:
            mutate_setting("volume_ceiling", max(VM_MIN_DB, min(VM_MAX_DB, db)))
            save_settings()
            msg = get_text("vlimit_set", locale).format(
                v=get_setting("volume_ceiling")
            )
        if is_interaction:
            await target.response.send_message(msg)
        else:
            await target.send(msg)

    async def execute_toggle(
        self,
        target: Union[discord.Interaction, commands.Context[Any]],
        setting_key: str,
        name_key: str,
    ) -> None:
        is_interaction = isinstance(target, discord.Interaction)
        user = target.user if is_interaction else target.author
        locale = target.locale if is_interaction else _FALLBACK_LOCALE
        if user.id != DISCORD_BOT_OWNER_ID:
            msg = get_text("no_permission", locale)
        else:
            val = toggle_setting(setting_key)
            save_settings()
            msg = get_text("setting_updated", locale).format(
                name=get_text(name_key, locale), val=val
            )
        if is_interaction:
            await target.response.send_message(msg)
        else:
            await target.send(msg)

    async def execute_toggle_commands(
        self, target: Union[discord.Interaction, commands.Context[Any]]
    ) -> None:
        is_interaction = isinstance(target, discord.Interaction)
        user = target.user if is_interaction else target.author
        locale = target.locale if is_interaction else _FALLBACK_LOCALE
        if user.id != DISCORD_BOT_OWNER_ID:
            msg = get_text("no_permission", locale)
        else:
            val = toggle_setting("only_owner_mode")
            save_settings()
            msg = get_text("setting_updated", locale).format(
                name=get_text("commands_toggle", locale), val=val
            )
        if is_interaction:
            await target.response.send_message(msg)
        else:
            await target.send(msg)

    async def execute_now(
        self, target: Union[discord.Interaction, commands.Context[Any]]
    ) -> None:
        locale = (
            target.locale
            if isinstance(target, discord.Interaction)
            else _FALLBACK_LOCALE
        )
        info = await asyncio.to_thread(self.spotify.get_track_info)
        vol = await asyncio.to_thread(self.vm.get_volume)
        muted = await asyncio.to_thread(self.vm.is_muted)
        embed = create_now_embed(locale, info, vol, muted)
        view = SpotifyControlView()
        if isinstance(target, discord.Interaction):
            await target.response.send_message(embed=embed, view=view)
        else:
            await target.send(embed=embed, view=view)

    async def execute_toggle_now(
        self, target: Union[discord.Interaction, commands.Context[Any]]
    ) -> None:
        is_interaction = isinstance(target, discord.Interaction)
        user = target.user if is_interaction else target.author
        locale = target.locale if is_interaction else _FALLBACK_LOCALE
        if user.id != DISCORD_BOT_OWNER_ID:
            text = get_text("no_permission", locale)
            if is_interaction:
                await target.response.send_message(text)
            else:
                await target.send(text)
            return

        enabled = toggle_setting("status_enabled")
        if enabled:
            info = await asyncio.to_thread(self.spotify.get_track_info)
            vol = await asyncio.to_thread(self.vm.get_volume)
            muted = await asyncio.to_thread(self.vm.is_muted)
            msg_obj = await target.channel.send(
                embed=create_now_embed(locale, info, vol, muted),
                view=SpotifyControlView(),
            )
            update_settings(
                {
                    "status_msg_id": msg_obj.id,
                    "status_channel_id": msg_obj.channel.id,
                }
            )
            res_msg = get_text("status_msg_on", locale)
        else:
            update_settings({"status_msg_id": None})
            res_msg = get_text("status_msg_off", locale)

        await self.presence.update_status_data()
        save_settings()
        if is_interaction:
            await target.response.send_message(res_msg)
        else:
            await target.send(res_msg)

    async def setup_hook(self) -> None:
        self.add_view(SpotifyControlView())
        install_profile_tracker(self, self.profile_tracker)
        await self.tree.sync()

    async def close(self) -> None:
        await self.profile_tracker.close()
        await super().close()


def create_bot(vm: VoicemeeterClient) -> MusicBot:
    spotify = SpotifyClient()
    bot = MusicBot(vm, spotify)
    register_all_commands(bot)
    register_all_events(bot)
    return bot


async def run_bot(bot: MusicBot, token: str | None = None) -> None:
    resolved = (token or DISCORD_BOT_TOKEN).strip()
    if not resolved:
        raise RuntimeError(
            "DISCORD_BOT_TOKEN is not set. Export it as an environment variable."
        )
    async with bot:
        await bot.start(resolved)