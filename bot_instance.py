"""Discord bot: slash commands, views, radio stream, presence updates."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Literal, Union

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from config import (
    COMMAND_PREFIX,
    DEFAULT_LOCALE,
    DISCORD_BOT_TOKEN,
    DISCORD_BOT_OWNER_ID,
    EMBED_COLOR,
    FADE_MAX_STEPS,
    FADE_STEP_DB,
    FADE_STEP_DELAY_SECONDS,
    FFMPEG_AFTER_ARGS,
    FFMPEG_BEFORE_ARGS,
    PRESENCE_UPDATE_INTERVAL_SECONDS,
    VM_MAX_DB,
    VM_MIN_DB,
    VM_OUTPUT_DEVICE,
    VOLUME_STEP_DB,
    get_setting,
    get_settings,
    get_text,
    mutate_setting,
    save_settings,
    toggle_setting,
    update_settings,
)
from profile_tracker import ProfileTracker, install as install_profile_tracker
from spotify_client import SpotifyClient, SpotifyTrackInfo
from voicemeeter_client import VoicemeeterClient

# Заголовок-заглушка для fallback-локали в местах без discord.Interaction
# (обычные !-команды, где нет interaction.locale). Управляется через
# DEFAULT_LOCALE в .env ("ru" или любое другое значение -> английский).
_FALLBACK_LOCALE: discord.Locale = (
    discord.Locale.russian if DEFAULT_LOCALE == "ru" else discord.Locale.american_english
)


@dataclass(frozen=True, slots=True)
class LiveStatusState:
    volume_db: float
    muted: bool
    track_title: str
    track_active: bool


class SpotifyControlView(discord.ui.View):
    """Persistent view — each button needs a stable custom_id for add_view()."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @staticmethod
    def _bot(interaction: discord.Interaction) -> MusicBot:
        client = interaction.client
        if not isinstance(client, MusicBot):
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
        await self._bot(interaction).execute_prev(interaction)

    @discord.ui.button(
        emoji="⏯️",
        style=discord.ButtonStyle.blurple,
        custom_id="xd_spotify:pause",
    )
    async def pause_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._bot(interaction).execute_pause(interaction)

    @discord.ui.button(
        emoji="⏭️",
        style=discord.ButtonStyle.gray,
        custom_id="xd_spotify:skip",
    )
    async def skip_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._bot(interaction).execute_skip(interaction)

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
        if await bot.is_allowed(interaction):
            muted = await asyncio.to_thread(bot.vm.toggle_mute)
            await bot.update_status_data(muted=muted)
            msg = get_text("muted" if muted else "unmuted", interaction.locale)
            await interaction.response.send_message(msg, ephemeral=True)


class MusicBot(commands.Bot):
    def __init__(self, vm: VoicemeeterClient, spotify: SpotifyClient) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True  # required for on_member_update (profile_tracker)
        super().__init__(command_prefix=COMMAND_PREFIX, intents=intents)
        self.vm = vm
        self.spotify = spotify
        self._last_track_name: str | None = None
        self._track_start_time: int = int(time.time())
        self._status_lock = asyncio.Lock()
        self.profile_tracker = ProfileTracker()

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

    def create_now_embed(
        self,
        locale: discord.Locale | str | None,
        info: SpotifyTrackInfo,
        vol: float,
        muted: bool,
    ) -> discord.Embed:
        title = (
            info.title
            if info.active
            else get_text("nothing_playing", locale)
        )
        mute_icon = "🔇" if muted else "🔊"
        bar_size = 10
        # bar_size шкала калибрована под диапазон VM_MIN_DB..VM_MAX_DB
        db_range = VM_MAX_DB - VM_MIN_DB
        filled = int(((vol - VM_MIN_DB) / db_range) * bar_size) if db_range else 0
        filled = max(0, min(bar_size, filled))
        bar = "▰" * filled + "▱" * (bar_size - filled)
        embed = discord.Embed(
            title=f"{mute_icon} {get_text('now_playing', locale)}",
            description=f"**{title}**",
            color=EMBED_COLOR,
        )
        embed.add_field(
            name=get_text("volume_bar", locale),
            value=f"`{bar}` {round(vol, 1)} dB",
            inline=False,
        )
        return embed

    async def vm_fade_volume(self, target_v: float) -> float:
        current = await asyncio.to_thread(self.vm.get_volume)
        steps = int(abs(target_v - current) / FADE_STEP_DB) if FADE_STEP_DB else 1
        steps = max(1, min(steps, FADE_MAX_STEPS))
        delta = (target_v - current) / steps
        value = current
        for _ in range(steps):
            value += delta
            await asyncio.to_thread(self.vm.set_volume, value)
            await asyncio.sleep(FADE_STEP_DELAY_SECONDS)
        return await asyncio.to_thread(self.vm.set_volume, target_v)

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
                if not self.vm.is_connected:
                    return

                vol = (
                    volume
                    if volume is not None
                    else await asyncio.to_thread(self.vm.get_volume)
                )
                is_muted = (
                    muted
                    if muted is not None
                    else await asyncio.to_thread(self.vm.is_muted)
                )

                if track_title is not None:
                    info = SpotifyTrackInfo(
                        title=track_title,
                        active=bool(track_active),
                    )
                elif refresh_track:
                    info = await asyncio.to_thread(
                        self.spotify.get_track_info
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
                if self.voice_clients:
                    vc = self.voice_clients[0]
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
                await self.change_presence(activity=activity)

                if get_setting("status_enabled") and get_setting("status_msg_id"):
                    channel = self.get_channel(
                        int(get_setting("status_channel_id") or 0)
                    )
                    if isinstance(channel, discord.TextChannel):
                        try:
                            msg = await channel.fetch_message(
                                int(get_setting("status_msg_id"))
                            )
                            await msg.edit(
                                embed=self.create_now_embed(
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

    @update_presence.before_loop
    async def _before_presence(self) -> None:
        await self.wait_until_ready()

    async def is_allowed(
        self, obj: Union[discord.Interaction, commands.Context[Any]]
    ) -> bool:
        is_interaction = isinstance(obj, discord.Interaction)
        guild = obj.guild
        if guild is None:
            return False

        owner = guild.get_member(DISCORD_BOT_OWNER_ID)
        user = obj.user if is_interaction else obj.author
        locale = (
            obj.locale
            if is_interaction
            else _FALLBACK_LOCALE
        )

        async def respond(text: str, *, ephemeral: bool = False) -> None:
            if is_interaction:
                if obj.response.is_done():
                    await obj.followup.send(text, ephemeral=ephemeral)
                else:
                    await obj.response.send_message(
                        text, ephemeral=ephemeral
                    )
            else:
                await obj.send(text)

        if (
            user.id != DISCORD_BOT_OWNER_ID
            and get_setting("only_owner_mode", False)
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
                await respond(
                    get_text("join_same_vc", locale), ephemeral=True
                )
                return False
        return True

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

    async def execute_pause(
        self, target: Union[discord.Interaction, commands.Context[Any]]
    ) -> None:
        if not await self.is_allowed(target):
            return
        locale = (
            target.locale
            if isinstance(target, discord.Interaction)
            else _FALLBACK_LOCALE
        )
        ok = await asyncio.to_thread(self.spotify.play_pause)
        msg = get_text("paused" if ok else "not_found", locale)
        await self.update_status_data()
        if isinstance(target, discord.Interaction):
            await target.response.send_message(msg)
        else:
            await target.send(msg)

    async def execute_skip(
        self, target: Union[discord.Interaction, commands.Context[Any]]
    ) -> None:
        if not await self.is_allowed(target):
            return
        locale = (
            target.locale
            if isinstance(target, discord.Interaction)
            else _FALLBACK_LOCALE
        )
        ok = await asyncio.to_thread(self.spotify.next_track)
        msg = get_text("skipped" if ok else "not_found", locale)
        await self.update_status_data()
        if isinstance(target, discord.Interaction):
            await target.response.send_message(msg)
        else:
            await target.send(msg)

    async def execute_prev(
        self, target: Union[discord.Interaction, commands.Context[Any]]
    ) -> None:
        if not await self.is_allowed(target):
            return
        locale = (
            target.locale
            if isinstance(target, discord.Interaction)
            else _FALLBACK_LOCALE
        )
        ok = await asyncio.to_thread(self.spotify.previous_track)
        msg = get_text("prev" if ok else "not_found", locale)
        await self.update_status_data()
        if isinstance(target, discord.Interaction):
            await target.response.send_message(msg)
        else:
            await target.send(msg)

    async def execute_prev2(
        self, target: Union[discord.Interaction, commands.Context[Any]]
    ) -> None:
        if not await self.is_allowed(target):
            return
        locale = (
            target.locale
            if isinstance(target, discord.Interaction)
            else _FALLBACK_LOCALE
        )
        ok = await asyncio.to_thread(self.spotify.previous_track_twice)
        msg = get_text("prev2" if ok else "not_found", locale)
        await self.update_status_data()
        if isinstance(target, discord.Interaction):
            await target.response.send_message(msg)
        else:
            await target.send(msg)

    async def execute_vol(
        self,
        target: Union[discord.Interaction, commands.Context[Any]],
        mode: Literal["set", "add", "rem"],
        value: float,
    ) -> None:
        if not await self.is_allowed(target):
            return
        is_interaction = isinstance(target, discord.Interaction)
        user = target.user if is_interaction else target.author
        locale = (
            target.locale if is_interaction else _FALLBACK_LOCALE
        )
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

        new_v = await self.vm_fade_volume(new_v)
        await self.update_status_data(volume=new_v)
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
        locale = (
            target.locale if is_interaction else _FALLBACK_LOCALE
        )
        if user.id != DISCORD_BOT_OWNER_ID:
            msg = get_text("no_permission", locale)
        else:
            # Потолок ограничен фактическим диапазоном Voicemeeter (VM_MIN_DB..VM_MAX_DB),
            # а не захардкоженными -60/12.
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
        locale = (
            target.locale if is_interaction else _FALLBACK_LOCALE
        )
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
        locale = (
            target.locale if is_interaction else _FALLBACK_LOCALE
        )
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
        embed = self.create_now_embed(locale, info, vol, muted)
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
        locale = (
            target.locale if is_interaction else _FALLBACK_LOCALE
        )
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
                embed=self.create_now_embed(locale, info, vol, muted),
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

        await self.update_status_data()
        save_settings()
        if is_interaction:
            await target.response.send_message(res_msg)
        else:
            await target.send(res_msg)

    async def setup_hook(self) -> None:
        self.add_view(SpotifyControlView())
        install_profile_tracker(self, self.profile_tracker)
        await self.tree.sync()

    async def on_ready(self) -> None:
        if not self.update_presence.is_running():
            self.update_presence.start()
        for guild in self.guilds:
            asyncio.create_task(self.profile_tracker.snapshot_all_members(guild))
        print(f"Logged in as {self.user} (Discord)")

    async def on_message(self, message: discord.Message) -> None:
        # Cheap "for free" profile capture: every message re-checks the
        # author's current nick/avatar, so changes are caught even without
        # a dedicated gateway event firing (record() no-ops if unchanged).
        if not message.author.bot:
            asyncio.create_task(
                self.profile_tracker.record(
                    user=message.author,
                    guild_id=message.guild.id if message.guild else None,
                    reason="message_seen",
                )
            )
        await self.process_commands(message)

    async def close(self) -> None:
        await self.profile_tracker.close()
        await super().close()

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.id != DISCORD_BOT_OWNER_ID:
            return
        if before.channel and after.channel is None and get_setting(
            "auto_leave"
        ):
            vc = member.guild.voice_client
            if vc:
                await vc.disconnect()
            return
        if (
            after.channel
            and before.channel != after.channel
            and get_setting("auto_join")
        ):
            vc = member.guild.voice_client
            if vc:
                await vc.move_to(after.channel)
            else:
                await after.channel.connect(self_deaf=True)
            await asyncio.sleep(1)
            await self.start_radio(member.guild)


def register_commands(bot: MusicBot) -> None:
    @bot.tree.command(name="pause", description="Pause or Resume Spotify")
    async def pause_cmd(interaction: discord.Interaction) -> None:
        await bot.execute_pause(interaction)

    @bot.tree.command(name="skip", description="Next track")
    async def skip_cmd(interaction: discord.Interaction) -> None:
        await bot.execute_skip(interaction)

    @bot.tree.command(name="prev", description="Previous track")
    async def prev_cmd(interaction: discord.Interaction) -> None:
        await bot.execute_prev(interaction)

    @bot.tree.command(name="prev2", description="Back 2 tracks")
    async def prev2_cmd(interaction: discord.Interaction) -> None:
        await bot.execute_prev2(interaction)

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

    @bot.tree.command(name="now", description="Current track and volume")
    async def now_cmd(interaction: discord.Interaction) -> None:
        await bot.execute_now(interaction)

    @bot.tree.command(
        name="toggle_now", description="Live status message (Owner)"
    )
    async def toggle_now_cmd(interaction: discord.Interaction) -> None:
        await bot.execute_toggle_now(interaction)

    @bot.tree.command(name="toggle_join", description="Auto-join VC (Owner)")
    async def toggle_join_cmd(interaction: discord.Interaction) -> None:
        await bot.execute_toggle(interaction, "auto_join", "join_auto")

    @bot.tree.command(name="toggle_leave", description="Auto-leave VC (Owner)")
    async def toggle_leave_cmd(interaction: discord.Interaction) -> None:
        await bot.execute_toggle(interaction, "auto_leave", "leave_auto")

    @bot.tree.command(
        name="toggle_others", description="Allow others in VC (Owner)"
    )
    async def toggle_others_cmd(interaction: discord.Interaction) -> None:
        await bot.execute_toggle(
            interaction, "allow_others_vc", "others_access"
        )

    @bot.tree.command(
        name="toggle_commands", description="Owner-only commands (Owner)"
    )
    async def toggle_commands_cmd(interaction: discord.Interaction) -> None:
        await bot.execute_toggle_commands(interaction)

    @bot.tree.command(name="mute", description="Mute/Unmute Strip[7]")
    async def mute_cmd(interaction: discord.Interaction) -> None:
        if await bot.is_allowed(interaction):
            muted = await asyncio.to_thread(bot.vm.toggle_mute)
            await bot.update_status_data(muted=muted)
            msg = get_text(
                "muted" if muted else "unmuted", interaction.locale
            )
            await interaction.response.send_message(msg)

    @bot.tree.command(name="join", description="Join and start radio")
    async def join_cmd(interaction: discord.Interaction) -> None:
        if await bot.is_allowed(interaction):
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

    @bot.command(name="pause")
    async def pause_p(ctx: commands.Context[Any]) -> None:
        await bot.execute_pause(ctx)

    @bot.command(name="skip")
    async def skip_p(ctx: commands.Context[Any]) -> None:
        await bot.execute_skip(ctx)

    @bot.command(name="prev")
    async def prev_p(ctx: commands.Context[Any]) -> None:
        await bot.execute_prev(ctx)

    @bot.command(name="prev2")
    async def prev2_p(ctx: commands.Context[Any]) -> None:
        await bot.execute_prev2(ctx)

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

    @bot.command(name="now")
    async def now_p(ctx: commands.Context[Any]) -> None:
        await bot.execute_now(ctx)

    @bot.command(name="toggle_now")
    async def toggle_now_p(ctx: commands.Context[Any]) -> None:
        await bot.execute_toggle_now(ctx)

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

    @bot.command(name="mute")
    async def mute_p(ctx: commands.Context[Any]) -> None:
        if await bot.is_allowed(ctx):
            muted = await asyncio.to_thread(bot.vm.toggle_mute)
            await bot.update_status_data(muted=muted)
            await ctx.send(
                get_text(
                    "muted" if muted else "unmuted", _FALLBACK_LOCALE
                )
            )


def create_bot(vm: VoicemeeterClient) -> MusicBot:
    spotify = SpotifyClient()
    bot = MusicBot(vm, spotify)
    register_commands(bot)
    return bot


async def run_bot(bot: MusicBot, token: str | None = None) -> None:
    resolved = (token or DISCORD_BOT_TOKEN).strip()
    if not resolved:
        raise RuntimeError(
            "DISCORD_TOKEN is not set. Export it as an environment variable."
        )
    async with bot:
        await bot.start(resolved)
