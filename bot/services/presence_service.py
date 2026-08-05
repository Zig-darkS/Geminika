from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import discord
from discord.ext import tasks

from bot.config import (
    DEFAULT_LOCALE,
    PRESENCE_UPDATE_INTERVAL_SECONDS,
    get_setting,
    get_text,
)
from spotify_client import SpotifyTrackInfo
from bot.services.embed_service import create_now_embed
from bot.views.spotify_control_view import SpotifyControlView

if TYPE_CHECKING:
    from bot.bot import MusicBot

_FALLBACK_LOCALE: discord.Locale = (
    discord.Locale.russian if DEFAULT_LOCALE == "ru" else discord.Locale.american_english
)


class PresenceService:
    def __init__(self, bot: MusicBot) -> None:
        self.bot = bot
        self._last_track_name: str | None = None
        self._track_start_time: int = int(time.time())
        self._status_lock = asyncio.Lock()

    async def update_status_data(
        self,
        *,
        refresh_track: bool = True,
        volume: float | None = None,
        muted: bool | None = None,
        track_title: str | None = None,
        track_active: bool | None = None,
    ) -> None:
        async with self._status_lock:
            try:
                if not self.bot.vm.is_connected:
                    return

                vol = (
                    volume
                    if volume is not None
                    else await asyncio.to_thread(self.bot.vm.get_volume)
                )
                is_muted = (
                    muted
                    if muted is not None
                    else await asyncio.to_thread(self.bot.vm.is_muted)
                )

                if track_title is not None:
                    info = SpotifyTrackInfo(
                        title=track_title,
                        active=bool(track_active),
                    )
                elif refresh_track:
                    info = await asyncio.to_thread(
                        self.bot.spotify.get_track_info
                    )
                else:
                    info = SpotifyTrackInfo(
                        title=self._last_track_name
                        or get_text("nothing_playing", DEFAULT_LOCALE),
                        active=bool(self._last_track_name),
                    )

                track_name = (
                    info.title
                    if info.active
                    else get_text("nothing_playing", DEFAULT_LOCALE)
                )

                if track_name != self._last_track_name:
                    self._last_track_name = track_name
                    self._track_start_time = int(time.time())

                mute_icon = "🔇" if is_muted else "🔊"
                vc_info = "Not in VC"
                guild_info = "Idle"
                if self.bot.voice_clients:
                    vc = self.bot.voice_clients[0]
                    guild_info = f"Server: {vc.guild.name}"
                    vc_info = f"Room: {vc.channel.name}"

                status_name = f"{mute_icon} {round(vol, 1)}dB | {track_name}"
                activity = discord.Activity(
                    type=discord.ActivityType.listening,
                    name=status_name,
                    details=guild_info,
                    state=vc_info,
                    timestamps={"start": self._track_start_time},
                )
                await self.bot.change_presence(activity=activity)

                if get_setting("status_enabled") and get_setting("status_msg_id"):
                    channel = self.bot.get_channel(
                        int(get_setting("status_channel_id") or 0)
                    )
                    if isinstance(channel, discord.TextChannel):
                        try:
                            msg = await channel.fetch_message(
                                int(get_setting("status_msg_id"))
                            )
                            await msg.edit(
                                embed=create_now_embed(
                                    _FALLBACK_LOCALE,
                                    info,
                                    vol,
                                    is_muted,
                                ),
                                view=SpotifyControlView(),
                            )
                        except (discord.NotFound, discord.HTTPException):
                            pass
            except Exception as exc:
                print(f"Presence error: {exc}")

    @tasks.loop(seconds=PRESENCE_UPDATE_INTERVAL_SECONDS)
    async def update_presence(self) -> None:
        await self.update_status_data()

    async def start_task(self) -> None:
        if not self.update_presence.is_running():
            self.update_presence.start()