"""cut_export.py — вырезает диапазон сообщений из history.json в cutedchat.json,
подставляет легенду медиа/ссылок и позволяет описывать их прямо во время экспорта.

ЗАПУСК:
1. Интерактивно (со всеми меню и выбором медиа):
   python cut_export.py

2. Через аргументы командной строки:
   python cut_export.py path/to/history.json 111 222 --out fight.json
   python cut_export.py path/to/history.json 111 222 --describe  # принудительно открыть описание медиа
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _common import (
    DEFAULT_INCLUDE_FIELDS,
    apply_field_filter,
    extract_media_items,
    find_all_history_files,
    is_local_path,
    load_cache,
    load_history,
    open_item,
    save_cache,
    slice_messages,
    try_auto_hint,
)

TOOLS_DIR = Path(__file__).resolve().parent
DEFAULT_CACHE = TOOLS_DIR / "media_descriptions.json"
EXPORTS_DIR = TOOLS_DIR.parent / "exports"


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Вырезать диапазон сообщений в cutedchat.json")
    p.add_argument("history", type=Path, nargs="?", default=None, help="Путь до history.json")
    p.add_argument("start_id", type=int, nargs="?", default=None, help="Начальный ID сообщения")
    p.add_argument("end_id", type=int, nargs="?", default=None, help="Конечный ID сообщения")
    p.add_argument("--out", type=Path, default=Path("cutedchat.json"), help="Путь к выходному файлу")
    p.add_argument("--cache", type=Path, default=DEFAULT_CACHE, help="Легенда от legend_builder.py")
    p.add_argument("--describe", action="store_true", help="Открыть интерактивное описание медиа")

    for field in DEFAULT_INCLUDE_FIELDS:
        flag = "--no-" + field.replace("_", "-")
        p.add_argument(flag, action="store_true", help=f"не включать поле '{field}'")

    return p


def select_history_interactively(base_dir: Path) -> Path:
    search_dir = base_dir if base_dir.exists() else Path.cwd()
    files = find_all_history_files(search_dir)

    if not files:
        sys.exit(f"Не найдено ни одного history.json в {search_dir.resolve()}")

    print("\nДоступные каналы и треды:")
    for idx, filepath in enumerate(files, 1):
        try:
            rel_path = filepath.relative_to(search_dir)
        except ValueError:
            rel_path = filepath
        print(f"  [{idx}] {rel_path}")

    while True:
        choice = input("\nВыберите номер папки экспорта: ").strip()
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(files):
                return files[idx - 1]
        print("Некорректный выбор. Введите число из списка.")


def prompt_int(prompt_text: str) -> int:
    while True:
        val = input(prompt_text).strip()
        if val.isdigit():
            return int(val)
        print("Ошибка: введите числовой ID.")


def prompt_describe_media(
    items_with_count: list[tuple[str, int]],
    cache: dict[str, dict[str, Any]],
    cache_path: Path,
) -> None:
    """Интерактивный выбор и описание медиа-записей из конкретного диапазона."""
    if not items_with_count:
        print("\nВ этом диапазоне нет медиа или ссылок.")
        return

    print("\n" + "=" * 50)
    print("Медиа и ссылки в вырезанном диапазоне:")
    print("=" * 50)
    
    for idx, (item, count) in enumerate(items_with_count, 1):
        curr_desc = (cache.get(item) or {}).get("description")
        status = f'"{curr_desc}"' if curr_desc else "❌ Нет описания"
        kind = "файл" if is_local_path(item) else "ссылка"
        print(f"  [{idx}] ({count}x) [{kind}] {item}")
        print(f"      Текущий статус: {status}")

    choice = input(
        "\nКакие медиа описать? (например: 1, 3, 4-6 | 'all' — все | Enter — пропустить): "
    ).strip()

    if not choice:
        return

    selected_indices: set[int] = set()
    if choice.lower() == "all":
        selected_indices = set(range(1, len(items_with_count) + 1))
    else:
        for part in choice.replace(",", " ").split():
            if "-" in part:
                subparts = part.split("-")
                if len(subparts) == 2 and subparts[0].isdigit() and subparts[1].isdigit():
                    start, end = int(subparts[0]), int(subparts[1])
                    for i in range(start, end + 1):
                        if 1 <= i <= len(items_with_count):
                            selected_indices.add(i)
            elif part.isdigit():
                idx = int(part)
                if 1 <= idx <= len(items_with_count):
                    selected_indices.add(idx)

    if not selected_indices:
        print("Ни одно медиа не выбрано.")
        return

    print(f"\nВыбрано медиа для обработки: {len(selected_indices)}\n")

    for idx in sorted(selected_indices):
        item, count = items_with_count[idx - 1]
        kind = "локальный файл" if is_local_path(item) else "ссылка"
        hint = try_auto_hint(item)

        print(f"[{idx}/{len(items_with_count)}] [{kind}] встречается {count}x: {item}")
        if hint:
            print(f"   Подсказка (авто): {hint}")

        open_item(item)
        try:
            raw = input(
                "   Описание (Enter=оставить/авто, 'skip'=пропустить, 'q'=выйти): "
            ).strip()
        except EOFError:
            raw = "q"

        if raw.lower() == "q":
            print("Описание прервано.")
            break

        if raw.lower() == "skip":
            cache[item] = {"count": count, "description": None, "source": "skipped"}
            save_cache(cache_path, cache)
            continue

        if raw == "":
            if hint:
                cache[item] = {"count": count, "description": hint, "source": "auto"}
                save_cache(cache_path, cache)
            continue

        cache[item] = {"count": count, "description": raw, "source": "manual"}
        save_cache(cache_path, cache)

    print("\n✅ Изменения легенды сохранены.")


def main() -> None:
    args = build_arg_parser().parse_args()
    is_interactive = args.history is None or args.start_id is None or args.end_id is None

    if is_interactive:
        print("=== Интерактивный режим cut_export ===")
        history_path = select_history_interactively(EXPORTS_DIR)
        start_id = prompt_int("Введите start_id: ")
        end_id = prompt_int("Введите end_id: ")

        out_input = input("Имя итогового файла [cutedchat.json]: ").strip()
        out_path = Path(out_input) if out_input else args.out
    else:
        history_path = args.history
        start_id = args.start_id
        end_id = args.end_id
        out_path = args.out

    include_fields = dict(DEFAULT_INCLUDE_FIELDS)
    for field in DEFAULT_INCLUDE_FIELDS:
        if getattr(args, "no_" + field):
            include_fields[field] = False

    messages = load_history(history_path)
    selected = slice_messages(messages, start_id, end_id)
    if not selected:
        sys.exit("В указанном диапазоне не найдено ни одного сообщения.")

    print(f"\nНайдено сообщений в диапазоне: {len(selected)}")

    cache = load_cache(args.cache)
    counter = extract_media_items(selected)
    media_items_ranked = counter.most_common()

    # Интерактивное описание медиа только из этой вырезки
    if is_interactive or args.describe:
        prompt_describe_media(media_items_ranked, cache, args.cache)

    media_legend = [
        {
            "item": item,
            "count": count,
            "description": (cache.get(item) or {}).get("description"),
            "source": (cache.get(item) or {}).get("source"),
        }
        for item, count in media_items_ranked
    ]
    undescribed = sum(1 for e in media_legend if e["description"] is None)
    if undescribed:
        print(f"⚠️  Осталось ссылок/медиа без описания: {undescribed}")

    trimmed = apply_field_filter(selected, include_fields)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_history": str(history_path),
        "range": {
            "start_id": start_id,
            "end_id": end_id,
            "message_count": len(trimmed),
        },
        "media_legend": media_legend,
        "messages": trimmed,
    }

    out_path.write_text(
        __import__("json").dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n✅ Готово: {out_path} ({len(trimmed)} сообщений, {len(media_legend)} медиа-записей)")


if __name__ == "__main__":
    main()