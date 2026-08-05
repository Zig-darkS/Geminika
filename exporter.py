"""Standalone full-server exporter, meant to be launched in its own
Windows Terminal window (real-time progress in stdout).

Usage:
    python exporter.py <guild_id>
    python exporter.py <guild_id> --recheck-limit 200 --recheck-max-age-hours 3

Exports, per guild:
    exports/<guild_id>_<guild_name>/
        server_structure.json      # categories -> channels tree
        <channel_id>_<channel_name>/
            history.json           # messages, oldest -> newest
            media/                 # attachments
        <channel_id>_<channel_name>/threads/<thread_id>_<thread_name>/
            history.json
            media/

Each message entry includes both the numeric snowflake id, the raw
username, and the resolved display name (guild nick > global display
name > username) so a later "fake discord viewer" site has everything
it needs. Threads (active + archived, public + private-if-permitted)
are walked too, not just plain channels.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import discord
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ.get("DISCORD_TOKEN", "").strip()
if not TOKEN:
    # fall back to the same token file the main bot uses
    try:
        from config import _load_discord_token  # type: ignore

        TOKEN = _load_discord_token()
    except Exception:
        pass

from config import EXPORT_ROOT

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)

# Заполняется в main() до client.run() — используется в on_ready(), у которого
# нет доступа к argparse-неймспейсу иначе (discord.py сам вызывает on_ready).
_CLI_ARGS: argparse.Namespace | None = None

# --- live progress counters -------------------------------------------------
_stats = {
    "messages": 0,
    "media": 0,
    "channels_done": 0,
    "channels_total": 0,
    "edited": 0,
    "deleted": 0,
}
_stats_lock = asyncio.Lock()


def _sanitize(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in (" ", "_", "-")).strip() or "unnamed"


def _display_name(author: discord.abc.User | discord.Member) -> str:
    # Member.display_name already resolves guild-nick -> global_name -> username
    return getattr(author, "display_name", None) or str(author)


async def _print_progress() -> None:
    """Background task: prints a running total once a second."""
    while True:
        async with _stats_lock:
            print(
                f"\r[progress] сообщений: {_stats['messages']} | "
                f"медиа: {_stats['media']} | "
                f"изменено: {_stats['edited']} | удалено: {_stats['deleted']} | "
                f"каналов: {_stats['channels_done']}/{_stats['channels_total']}   ",
                end="",
                flush=True,
            )
        await asyncio.sleep(1.0)


async def _recheck_recent_messages(
    channel: discord.abc.Messageable,
    messages_data: list[dict[str, Any]],
    limit: int = 100,
    max_age_hours: float = 1.0,
) -> tuple[int, int]:
    """Re-fetch recently-saved messages to catch edits/deletes that happened
    after the previous export run. Only messages created within the last
    `max_age_hours` are considered (capped at `limit`), since older messages
    are extremely unlikely to still be edited/deleted in practice.
    Updates `messages_data` in place. Returns (edited_count, deleted_count).
    """
    if not messages_data:
        return 0, 0

    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    def _created_at(entry: dict[str, Any]) -> datetime | None:
        raw = entry.get("created_at")
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    candidates = [
        m
        for m in messages_data
        if not m.get("deleted")
        and (ts := _created_at(m)) is not None
        and ts >= cutoff
    ]
    candidates.sort(key=lambda m: m["message_id"])
    candidates = candidates[-limit:]

    edited = 0
    deleted = 0
    for entry in candidates:
        msg_id = entry["message_id"]
        try:
            fresh = await channel.fetch_message(msg_id)
        except discord.NotFound:
            entry["deleted"] = True
            entry["deleted_detected_at"] = _now_iso_module()
            deleted += 1
            print(f"\n    [удалено] сообщение {msg_id} от {entry.get('author_display_name')}")
            continue
        except discord.Forbidden:
            break
        except Exception:
            continue

        fresh_edited_at = fresh.edited_at.isoformat() if fresh.edited_at else None
        if fresh.content != entry.get("content") or fresh_edited_at != entry.get("edited_at"):
            entry["content"] = fresh.content
            entry["edited_at"] = fresh_edited_at
            entry["reactions"] = [
                {"emoji": str(r.emoji), "count": r.count} for r in fresh.reactions
            ]
            edited += 1
            print(f"\n    [изменено] сообщение {msg_id} от {entry.get('author_display_name')}")

    return edited, deleted


def _now_iso_module() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


async def _export_message_stream(
    channel: discord.abc.Messageable,
    base_dir: Path,
    *,
    recheck_limit: int,
    recheck_max_age_hours: float,
) -> int:
    """Export message history, resuming from where a previous run left off.

    If history.json already exists:
    - the last up to `recheck_limit` saved messages are re-fetched to catch
      edits/deletes that happened since the previous run (see
      _recheck_recent_messages).
    - only messages newer than the last saved message_id are then fetched
      (via history(after=...)) and appended.
    Existing entries and already-downloaded media are otherwise left
    untouched, so repeated runs are cheap.
    """
    media_dir = base_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    history_path = base_dir / "history.json"

    messages_data: list[dict[str, Any]] = []
    resume_after: discord.Object | None = None
    if history_path.is_file():
        try:
            messages_data = json.loads(history_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            messages_data = []
        if messages_data:
            last_id = max(m["message_id"] for m in messages_data)
            resume_after = discord.Object(id=last_id)

    edited_n, deleted_n = await _recheck_recent_messages(
        channel,
        messages_data,
        limit=recheck_limit,
        max_age_hours=recheck_max_age_hours,
    )
    if edited_n or deleted_n:
        async with _stats_lock:
            _stats["edited"] += edited_n
            _stats["deleted"] += deleted_n
        history_path.write_text(
            json.dumps(messages_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    new_count = 0
    async for msg in channel.history(
        limit=None, oldest_first=True, after=resume_after
    ):
        attachments_info = []
        for att in msg.attachments:
            file_path = media_dir / f"{msg.id}_{att.filename}"
            try:
                if not file_path.is_file():
                    await att.save(file_path)
                attachments_info.append(
                    {
                        "attachment_id": att.id,
                        "filename": att.filename,
                        "local_path": str(file_path),
                        "size_bytes": att.size,
                        "content_type": att.content_type,
                    }
                )
                async with _stats_lock:
                    _stats["media"] += 1
            except Exception as exc:
                print(f"\n    [file error] {att.filename}: {exc}")

        edited_at = msg.edited_at.isoformat() if msg.edited_at else None
        reply_to = None
        if msg.reference and msg.reference.message_id:
            reply_to = msg.reference.message_id

        messages_data.append(
            {
                "message_id": msg.id,
                "author_id": msg.author.id,
                "author_username": str(msg.author),
                "author_display_name": _display_name(msg.author),
                "author_avatar_url": str(msg.author.display_avatar.url)
                if msg.author.display_avatar
                else None,
                "created_at": msg.created_at.isoformat(),
                "edited_at": edited_at,
                "content": msg.content,
                "reply_to_message_id": reply_to,
                "reactions": [
                    {"emoji": str(r.emoji), "count": r.count} for r in msg.reactions
                ],
                "attachments": attachments_info,
            }
        )
        new_count += 1
        async with _stats_lock:
            _stats["messages"] += 1

    if new_count:
        history_path.write_text(
            json.dumps(messages_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return new_count


async def _export_channel_with_threads(
    channel: discord.TextChannel,
    guild_dir: Path,
    *,
    recheck_limit: int,
    recheck_max_age_hours: float,
) -> None:
    safe_name = _sanitize(channel.name)
    chan_dir = guild_dir / f"{channel.id}_{safe_name}"
    chan_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n--> Канал: #{channel.name}")
    try:
        n = await _export_message_stream(
            channel,
            chan_dir,
            recheck_limit=recheck_limit,
            recheck_max_age_hours=recheck_max_age_hours,
        )
        print(f"\n    Готово: +{n} новых сообщений.")
    except discord.Forbidden:
        print(f"\n    [пропуск] нет прав на чтение #{channel.name}")
    except Exception as exc:
        print(f"\n    [ошибка канала] #{channel.name}: {exc}")

    # --- threads: active + archived (public & private) ---
    threads_dir = chan_dir / "threads"
    all_threads: list[discord.Thread] = list(channel.threads)
    try:
        async for t in channel.archived_threads(limit=None):
            all_threads.append(t)
    except discord.Forbidden:
        pass
    except Exception as exc:
        print(f"\n    [ошибка архивных тредов] #{channel.name}: {exc}")
    try:
        async for t in channel.archived_threads(limit=None, private=True):
            all_threads.append(t)
    except (discord.Forbidden, Exception):
        pass

    seen_ids: set[int] = set()
    for thread in all_threads:
        if thread.id in seen_ids:
            continue
        seen_ids.add(thread.id)
        safe_tname = _sanitize(thread.name)
        thread_dir = threads_dir / f"{thread.id}_{safe_tname}"
        thread_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n    --> Ветка: {thread.name}")
        try:
            n = await _export_message_stream(
                thread,
                thread_dir,
                recheck_limit=recheck_limit,
                recheck_max_age_hours=recheck_max_age_hours,
            )
            print(f"\n        Готово: +{n} новых сообщений.")
        except discord.Forbidden:
            print(f"\n        [пропуск] нет прав на ветку {thread.name}")
        except Exception as exc:
            print(f"\n        [ошибка ветки] {thread.name}: {exc}")

    async with _stats_lock:
        _stats["channels_done"] += 1


def _dump_server_structure(guild: discord.Guild, guild_dir: Path) -> None:
    """Save category -> channel tree, so a later viewer can render the sidebar."""
    structure: dict[str, Any] = {
        "guild_id": guild.id,
        "guild_name": guild.name,
        "icon_url": str(guild.icon.url) if guild.icon else None,
        "categories": [],
        "uncategorized": [],
    }
    for category in guild.categories:
        cat_entry = {
            "id": category.id,
            "name": category.name,
            "position": category.position,
            "channels": [
                {"id": ch.id, "name": ch.name, "type": str(ch.type), "position": ch.position}
                for ch in sorted(category.channels, key=lambda c: c.position)
            ],
        }
        structure["categories"].append(cat_entry)

    for ch in guild.channels:
        if ch.category is None:
            structure["uncategorized"].append(
                {"id": ch.id, "name": ch.name, "type": str(ch.type), "position": ch.position}
            )

    (guild_dir / "server_structure.json").write_text(
        json.dumps(structure, ensure_ascii=False, indent=2), encoding="utf-8"
    )


async def run_export(
    guild_id: int, *, recheck_limit: int, recheck_max_age_hours: float
) -> None:
    await client.wait_until_ready()
    guild = client.get_guild(guild_id)
    if not guild:
        print(f"Сервер с ID {guild_id} не найден (бот не состоит в нём?).")
        await client.close()
        return

    safe_guild = _sanitize(guild.name)
    guild_dir = EXPORT_ROOT / f"{guild.id}_{safe_guild}"
    guild_dir.mkdir(parents=True, exist_ok=True)

    print(f"Начинаем полную выгрузку сервера: {guild.name}")
    _dump_server_structure(guild, guild_dir)

    text_channels = [
        ch for ch in guild.channels if isinstance(ch, discord.TextChannel)
    ]
    async with _stats_lock:
        _stats["channels_total"] = len(text_channels)

    progress_task = asyncio.create_task(_print_progress())

    start = time.monotonic()
    for channel in text_channels:
        await _export_channel_with_threads(
            channel,
            guild_dir,
            recheck_limit=recheck_limit,
            recheck_max_age_hours=recheck_max_age_hours,
        )

    progress_task.cancel()
    elapsed = time.monotonic() - start
    print(
        f"\n\n✅ Выгрузка завершена за {elapsed:.1f}s: "
        f"+{_stats['messages']} новых сообщений, +{_stats['media']} новых файлов медиа, "
        f"{_stats['edited']} изменено, {_stats['deleted']} удалено."
    )
    print(f"Файлы: {guild_dir}")
    await client.close()


@client.event
async def on_ready() -> None:
    print(f"Вход выполнен: {client.user}")
    assert _CLI_ARGS is not None
    asyncio.create_task(
        run_export(
            _CLI_ARGS.guild_id,
            recheck_limit=_CLI_ARGS.recheck_limit,
            recheck_max_age_hours=_CLI_ARGS.recheck_max_age_hours,
        )
    )


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Полная выгрузка истории Discord-сервера")
    p.add_argument("guild_id", type=int)
    p.add_argument(
        "--recheck-limit",
        type=int,
        default=100,
        help="Сколько последних сообщений перепроверять на правки/удаления (по умолчанию 100)",
    )
    p.add_argument(
        "--recheck-max-age-hours",
        type=float,
        default=1.0,
        help="Не перепроверять сообщения старше этого возраста, в часах (по умолчанию 1.0)",
    )
    return p


def main() -> None:
    global _CLI_ARGS
    _CLI_ARGS = build_arg_parser().parse_args()

    if not TOKEN:
        print("DISCORD_TOKEN не найден (переменная окружения или token.txt).")
        sys.exit(1)
    try:
        client.run(TOKEN)
    except KeyboardInterrupt:
        pass
    print("\nНажмите Enter для закрытия окна...")
    try:
        input()
    except EOFError:
        pass


if __name__ == "__main__":
    main()
