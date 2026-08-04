"""cut_export.py — вырезает диапазон сообщений из history.json в cutedchat.json
и подставляет сверху уже готовую легенду медиа/ссылок (построенную заранее
через legend_builder.py). Никаких сетевых запросов и вопросов тут не задаёт —
чисто механическая резка + подстановка.

ЗАПУСК:
    python cut_export.py путь/до/history.json 1531422951667269774 1531423001667269999
    python cut_export.py ../exports/123_Guild/456_general/history.json 111 222 --out fight.json
    python cut_export.py ... 111 222 --no-author-id --no-author-avatar-url

Если для какой-то ссылки/медиа из диапазона легенда ещё не готова — она всё
равно попадёт в media_legend с description=null (значит: сначала прогони
legend_builder.py по этому диапазону, если хочешь его описать).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from _common import (
    DEFAULT_INCLUDE_FIELDS,
    apply_field_filter,
    extract_media_items,
    load_cache,
    load_history,
    slice_messages,
)

TOOLS_DIR = Path(__file__).resolve().parent
DEFAULT_CACHE = TOOLS_DIR / "media_descriptions.json"


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Вырезать диапазон сообщений в cutedchat.json")
    p.add_argument("history", type=Path, help="Путь до history.json канала/треда")
    p.add_argument("start_id", type=int)
    p.add_argument("end_id", type=int)
    p.add_argument("--out", type=Path, default=Path("cutedchat.json"))
    p.add_argument("--cache", type=Path, default=DEFAULT_CACHE, help="Легенда от legend_builder.py")

    for field in DEFAULT_INCLUDE_FIELDS:
        flag = "--no-" + field.replace("_", "-")
        p.add_argument(flag, action="store_true", help=f"не включать поле '{field}'")

    return p


def main() -> None:
    args = build_arg_parser().parse_args()

    include_fields = dict(DEFAULT_INCLUDE_FIELDS)
    for field in DEFAULT_INCLUDE_FIELDS:
        if getattr(args, "no_" + field):
            include_fields[field] = False

    messages = load_history(args.history)
    selected = slice_messages(messages, args.start_id, args.end_id)
    if not selected:
        sys.exit("В указанном диапазоне не найдено ни одного сообщения.")

    print(f"Найдено сообщений в диапазоне: {len(selected)}")

    cache = load_cache(args.cache)
    counter = extract_media_items(selected)

    media_legend = [
        {
            "item": item,
            "count": count,
            "description": (cache.get(item) or {}).get("description"),
            "source": (cache.get(item) or {}).get("source"),
        }
        for item, count in counter.most_common()
    ]
    undescribed = sum(1 for e in media_legend if e["description"] is None)
    if undescribed:
        print(
            f"⚠️  {undescribed} ссылок/медиа в этом диапазоне ещё без описания "
            f"(прогони legend_builder.py, если хочешь их описать)."
        )

    trimmed = apply_field_filter(selected, include_fields)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_history": str(args.history),
        "range": {
            "start_id": args.start_id,
            "end_id": args.end_id,
            "message_count": len(trimmed),
        },
        "media_legend": media_legend,
        "messages": trimmed,
    }

    args.out.write_text(
        __import__("json").dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n✅ Готово: {args.out} ({len(trimmed)} сообщений, {len(media_legend)} медиа-записей)")


if __name__ == "__main__":
    main()