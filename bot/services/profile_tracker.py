"""Tracks nickname/avatar changes for guild members over time.

Design goals (per user request):
- Store display name (guild nick if set, else global display name) history.
- Store avatar (guild avatar if set, else global avatar) history, downloading
  the actual image bytes so a later "fake Discord viewer" website can render
  the exact avatar a user had at message-send time.
- Cheap: only writes when something actually changed, keyed by user id.
- Thread-safe enough for asyncio single-loop use (no external threads touch
  this except via asyncio.to_thread for file IO).

On-disk layout (under EXPORT_ROOT / "profiles"):
    profiles/
        <user_id>/
            history.json         # list of ProfileSnapshot dicts, oldest -> newest
            avatars/
                <sha1_of_url_or_hash>.png   # cached avatar images

history.json entries:
    {
        "timestamp": "2026-07-28T12:34:56+00:00",
        "guild_id": 123 | null,
        "display_name": "Bob",
        "username": "bob#0",           # username or username#discrim (legacy)
        "global_name": "Bob R.",
        "avatar_key": "a1b2c3d4.png" | null,   # filename inside avatars/, null if default
        "avatar_url": "https://cdn.discordapp.com/...",
        "reason": "nick_change" | "avatar_change" | "initial_snapshot" | "global_name_change"
    }
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import aiohttp
import discord

from bot.config import EXPORT_ROOT

PROFILES_DIR: Path = EXPORT_ROOT / "profiles"


@dataclass(slots=True)
class ProfileSnapshot:
    timestamp: str
    guild_id: Optional[int]
    display_name: str
    username: str
    global_name: Optional[str]
    avatar_key: Optional[str]
    avatar_url: Optional[str]
    reason: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _user_dir(user_id: int) -> Path:
    d = PROFILES_DIR / str(user_id)
    (d / "avatars").mkdir(parents=True, exist_ok=True)
    return d


def _load_history(user_id: int) -> list[dict[str, Any]]:
    path = _user_dir(user_id) / "history.json"
    if not path.is_file():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _save_history(user_id: int, history: list[dict[str, Any]]) -> None:
    path = _user_dir(user_id) / "history.json"
    path.write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )


class ProfileTracker:
    """Attach to a running bot: call `install(bot)` once in setup_hook/on_ready."""

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _download_avatar(self, url: str, user_id: int) -> str | None:
        """Download avatar bytes, return the local filename (or None on failure)."""
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.read()
        except Exception as exc:
            print(f"[profile_tracker] avatar download failed for {user_id}: {exc}")
            return None

        ext = ".png"
        if ".webp" in url:
            ext = ".webp"
        elif ".gif" in url:
            ext = ".gif"
        elif ".jpg" in url or ".jpeg" in url:
            ext = ".jpg"

        import hashlib

        key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ext
        out_path = _user_dir(user_id) / "avatars" / key
        if not out_path.is_file():
            out_path.write_bytes(data)
        return key

    async def record(
        self,
        *,
        user: discord.abc.User | discord.Member,
        guild_id: int | None,
        reason: str,
    ) -> None:
        """Record a snapshot if it differs from the last known one for this user."""
        async with self._lock:
            user_id = user.id
            display_name = getattr(user, "display_name", None) or str(user)
            username = str(user)
            global_name = getattr(user, "global_name", None)
            avatar_asset = user.display_avatar
            avatar_url = str(avatar_asset.url) if avatar_asset else None

            history = _load_history(user_id)
            last = history[-1] if history else None

            changed = (
                last is None
                or last.get("display_name") != display_name
                or last.get("avatar_url") != avatar_url
                or last.get("global_name") != global_name
            )
            if not changed:
                return

            avatar_key = None
            if avatar_url:
                avatar_key = await self._download_avatar(avatar_url, user_id)

            snap = ProfileSnapshot(
                timestamp=_now_iso(),
                guild_id=guild_id,
                display_name=display_name,
                username=username,
                global_name=global_name,
                avatar_key=avatar_key,
                avatar_url=avatar_url,
                reason=reason,
            )
            history.append(asdict(snap))
            await asyncio.to_thread(_save_history, user_id, history)
            print(
                f"[profile_tracker] {reason}: {username} -> "
                f"display='{display_name}' avatar={'yes' if avatar_key else 'no'}"
            )

    async def snapshot_all_members(self, guild: discord.Guild) -> None:
        """Baseline snapshot of every member, used once on startup / on demand."""
        for member in guild.members:
            await self.record(user=member, guild_id=guild.id, reason="initial_snapshot")

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


def install(bot: discord.Client, tracker: ProfileTracker) -> None:
    """Wire up member/user update listeners on an existing bot instance.

    Call this once, e.g. inside MusicBot.setup_hook().
    """

    @bot.event
    async def on_member_update(before: discord.Member, after: discord.Member) -> None:
        if before.nick != after.nick or before.display_avatar.url != after.display_avatar.url:
            await tracker.record(
                user=after,
                guild_id=after.guild.id,
                reason="nick_change" if before.nick != after.nick else "avatar_change",
            )

    @bot.event
    async def on_user_update(before: discord.User, after: discord.User) -> None:
        if before.name != after.name or before.avatar != after.avatar or getattr(
            before, "global_name", None
        ) != getattr(after, "global_name", None):
            await tracker.record(
                user=after,
                guild_id=None,
                reason="global_name_change" if before.name != after.name else "avatar_change",
            )
