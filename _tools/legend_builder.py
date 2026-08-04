"""legend_builder.py — сканирует все history.json в exports/ (или указанный
путь), находит все ссылки/медиа-вложения, считает частоту и даёт ТЕБЕ вручную
описать те, что реально повторяются (по умолчанию 2+ раза — то, что
встретилось один раз, почти наверняка не стоит времени, поэтому пропускается
автоматически и даже не спрашивается).

Ничего не режет и не экспортирует чат — только копит легенду в
media_descriptions.json. Второй инструмент (cut_export.py) её потом читает
и подставляет в готовый файл.

ЗАПУСК (из папки _tools или откуда угодно, путь ниже — просто дефолт):
    python legend_builder.py
    python legend_builder.py --min-count 3
    python legend_builder.py --dir ../exports/123_MyGuild
    python legend_builder.py --no-auto        # без подсказок из oEmbed
    python legend_builder.py --recheck        # пересмотреть уже описанное

Во время описания:
    Enter (без текста)   -> использовать подсказку сверху (если есть),
                             иначе просто пропустить в этой сессии (спросит снова в другой раз)
    "skip"                -> пропустить НАВСЕГДА (больше не спросит)
    "q"                   -> прервать сессию (остальное — в другой раз)
    любой другой текст     -> сохранить как описание (твой вариант)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common import (
    extract_media_items,
    find_all_history_files,
    is_local_path,
    load_cache,
    load_history,
    open_item,
    save_cache,
    try_auto_hint,
)

TOOLS_DIR = Path(__file__).resolve().parent
DEFAULT_SCAN_DIR = TOOLS_DIR.parent / "exports"
DEFAULT_CACHE = TOOLS_DIR / "media_descriptions.json"


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Построить/пополнить легенду медиа-описаний")
    p.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_SCAN_DIR,
        help=f"Где искать history.json (по умолчанию: {DEFAULT_SCAN_DIR})",
    )
    p.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    p.add_argument(
        "--min-count",
        type=int,
        default=2,
        help="Не спрашивать про то, что встретилось реже (по умолчанию 2)",
    )
    p.add_argument("--limit-new", type=int, default=30, help="Максимум новых вопросов за сессию")
    p.add_argument("--no-auto", action="store_true", help="Не показывать подсказки из oEmbed")
    p.add_argument(
        "--recheck",
        action="store_true",
        help="Спросить заново даже то, что уже есть в кэше (кроме помеченного 'skip')",
    )
    return p


def main() -> None:
    args = build_arg_parser().parse_args()

    files = find_all_history_files(args.dir)
    if not files:
        sys.exit(f"Не найдено ни одного history.json в {args.dir}")

    print(f"Сканирую {len(files)} файл(ов) history.json из {args.dir} ...")

    from collections import Counter

    total_counter: Counter[str] = Counter()
    for f in files:
        messages = load_history(f)
        total_counter.update(extract_media_items(messages))

    ranked = [
        (item, count) for item, count in total_counter.most_common() if count >= args.min_count
    ]
    skipped_rare = len(total_counter) - len(ranked)
    print(
        f"Уникальных ссылок/медиа всего: {len(total_counter)}. "
        f"Встретились {args.min_count}+ раз: {len(ranked)} "
        f"(разово — {skipped_rare}, пропущены автоматически)."
    )

    cache = load_cache(args.cache)

    to_ask = []
    for item, count in ranked:
        cached = cache.get(item)
        if cached and not args.recheck:
            continue  # уже описано или явно пропущено раньше
        to_ask.append((item, count))

    if not to_ask:
        print("Всё, что стоило описать, уже описано. Нечего спрашивать.")
        return

    print(f"К описанию: {len(to_ask)} (лимит за сессию: {args.limit_new})\n")

    asked = 0
    described = 0
    for item, count in to_ask:
        if asked >= args.limit_new:
            print(f"\n[лимит] --limit-new={args.limit_new} достигнут, останавливаюсь.")
            break
        asked += 1

        hint = None if args.no_auto else try_auto_hint(item)
        kind = "локальный файл" if is_local_path(item) else "ссылка"
        print(f"[{kind}] встречается {count}x: {item}")
        if hint:
            print(f"   подсказка (авто): {hint}")

        open_item(item)
        try:
            raw = input(
                "   Описание (Enter=подсказка/пропуск, 'skip'=навсегда, 'q'=выйти): "
            ).strip()
        except EOFError:
            raw = "q"

        if raw.lower() == "q":
            print("Прервано, остальное спросится в другой раз.")
            break

        if raw.lower() == "skip":
            cache[item] = {"count": count, "description": None, "source": "skipped"}
            save_cache(args.cache, cache)
            continue

        if raw == "":
            if hint:
                cache[item] = {"count": count, "description": hint, "source": "auto"}
                save_cache(args.cache, cache)
                described += 1
            # иначе — ничего не сохраняем, спросим в другой раз
            continue

        cache[item] = {"count": count, "description": raw, "source": "manual"}
        save_cache(args.cache, cache)
        described += 1

    print(f"\n✅ Описано в этой сессии: {described}. Легенда сохранена в {args.cache}")


if __name__ == "__main__":
    main()