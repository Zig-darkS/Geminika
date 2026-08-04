"""Общий код для _tools/legend_builder.py и _tools/cut_export.py.

Не запускается напрямую.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, quote

try:
    import requests
except ImportError:
    requests = None  # авто-подсказки через oEmbed просто отключатся

URL_RE = re.compile(r"https?://\S+")

# Какие поля сообщения оставлять в cutedchat.json по умолчанию.
DEFAULT_INCLUDE_FIELDS: dict[str, bool] = {
    "message_id": True,
    "author_id": True,
    "author_username": True,
    "author_display_name": True,
    "author_avatar_url": True,
    "created_at": True,
    "edited_at": True,
    "content": True,
    "reply_to_message_id": True,
    "reactions": True,
    "attachments": True,
    "deleted": True,
}

# Домены, для которых можно попробовать авто-подсказку через oEmbed
# (используется только как ПОДСКАЗКА в legend_builder — финальное описание
# всё равно пишет человек, потому что авто-текст обычно не передаёт суть).
OEMBED_ENDPOINTS: dict[str, str] = {
    "tenor.com": "https://tenor.com/oembed?url={url}",
    "youtube.com": "https://www.youtube.com/oembed?url={url}&format=json",
    "youtu.be": "https://www.youtube.com/oembed?url={url}&format=json",
    "giphy.com": "https://giphy.com/services/oembed?url={url}",
    "media.giphy.com": "https://giphy.com/services/oembed?url={url}",
    "vimeo.com": "https://vimeo.com/api/oembed.json?url={url}",
}


# --------------------------------------------------------------------- #
# history.json IO
# --------------------------------------------------------------------- #


def load_history(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        sys.exit(f"Не найден {path}.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"{path} повреждён: {exc}")
    if not isinstance(data, list):
        sys.exit(f"{path}: неожиданный формат (ожидался список сообщений).")
    return data


def find_all_history_files(root: Path) -> list[Path]:
    """Рекурсивно находит все history.json под root (каналы + треды)."""
    if root.is_file() and root.name == "history.json":
        return [root]
    return sorted(root.rglob("history.json"))


def slice_messages(
    messages: list[dict[str, Any]], start_id: int, end_id: int
) -> list[dict[str, Any]]:
    lo, hi = sorted((start_id, end_id))
    selected = [m for m in messages if lo <= m.get("message_id", -1) <= hi]
    selected.sort(key=lambda m: m.get("message_id", 0))
    return selected


def apply_field_filter(
    messages: list[dict[str, Any]], include: dict[str, bool]
) -> list[dict[str, Any]]:
    return [{k: v for k, v in m.items() if include.get(k, True)} for m in messages]


# --------------------------------------------------------------------- #
# Извлечение медиа/ссылок
# --------------------------------------------------------------------- #


def extract_media_items(messages: list[dict[str, Any]]) -> Counter[str]:
    """Counter: ключ — url или локальный путь к вложению, значение — частота."""
    counter: Counter[str] = Counter()
    for m in messages:
        content = m.get("content") or ""
        for url in URL_RE.findall(content):
            counter[url.rstrip(").,>\"'")] += 1
        for att in m.get("attachments") or []:
            local_path = att.get("local_path")
            if local_path:
                counter[local_path] += 1
    return counter


def is_local_path(item: str) -> bool:
    return not item.startswith("http://") and not item.startswith("https://")


def open_item(item: str) -> None:
    import webbrowser

    try:
        if is_local_path(item):
            p = Path(item)
            if sys.platform == "win32":
                import os

                os.startfile(p)  # type: ignore[attr-defined]
            else:
                webbrowser.open(p.as_uri())
        else:
            webbrowser.open(item)
    except Exception as exc:
        print(f"    (не удалось открыть: {exc})")


def try_auto_hint(url: str) -> str | None:
    """Возвращает подсказку из oEmbed — НЕ финальное описание, просто наводка."""
    if requests is None or is_local_path(url):
        return None
    domain = urlparse(url).netloc.lower().removeprefix("www.")
    endpoint_tmpl = OEMBED_ENDPOINTS.get(domain)
    if not endpoint_tmpl:
        return None
    endpoint = endpoint_tmpl.format(url=quote(url, safe=""))
    try:
        resp = requests.get(endpoint, timeout=6)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception:
        return None
    title = data.get("title")
    author = data.get("author_name")
    if title and author and domain in ("youtube.com", "youtu.be", "vimeo.com"):
        return f"{title} — {author}"
    return title or None


# --------------------------------------------------------------------- #
# Кэш легенды (общий на все чаты, накопительный)
# --------------------------------------------------------------------- #


def load_cache(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(path: Path, cache: dict[str, dict[str, Any]]) -> None:
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")