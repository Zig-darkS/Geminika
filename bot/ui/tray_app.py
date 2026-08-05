"""System tray UI — runs in a background thread (pystray)."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import pystray
from PIL import Image, ImageDraw

from bot.config import get_setting, save_settings, toggle_setting

from bot.config import BASE_DIR, get_setting, save_settings, toggle_setting

if TYPE_CHECKING:
    from bot.bot import MusicBot

ICON_PATH = BASE_DIR / "icon.png"

def load_tray_image(icon_path: Path | None = None) -> Image.Image:
    """Load tray icon from *icon.png* or build a simple fallback."""
    path = icon_path or ICON_PATH
    if path.is_file():
        with Image.open(path) as img:
            return img.convert("RGBA").copy()
    return create_default_tray_image()


def create_default_tray_image(size: int = 64) -> Image.Image:
    """Fallback icon when icon.png is missing."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = size // 8
    draw.ellipse(
        (margin, margin, size - margin, size - margin),
        fill=(29, 185, 84, 255),
    )
    bar_w = max(2, size // 10)
    cx = size // 2
    for i, h_mul in enumerate((0.35, 0.55, 0.45, 0.7)):
        x = cx + (i - 1.5) * (bar_w + 2)
        h = int(size * h_mul)
        y0 = (size - h) // 2
        draw.rectangle((x, y0, x + bar_w, y0 + h), fill=(255, 255, 255, 230))
    return img


class TrayApp:
    def __init__(self, bot: MusicBot, loop: asyncio.AbstractEventLoop) -> None:
        self._bot = bot
        self._loop = loop
        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None

    def _schedule(self, coro) -> None:
        asyncio.run_coroutine_threadsafe(coro, self._loop)

    def _make_toggle(self, key: str) -> Callable[[pystray.Icon, pystray.MenuItem], None]:
        def action(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
            toggle_setting(key)
            save_settings()

        return action

    def _is_checked(self, key: str) -> Callable[[pystray.MenuItem], bool]:
        return lambda _item: bool(get_setting(key, False))

    def _on_refresh(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self._schedule(self._bot.update_status_data())

    def _on_pause(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        async def _work() -> None:
            await asyncio.to_thread(self._bot.spotify.play_pause)
            await self._bot.update_status_data()

        self._schedule(_work())

    def _on_skip(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        async def _work() -> None:
            await asyncio.to_thread(self._bot.spotify.next_track)
            await self._bot.update_status_data()

        self._schedule(_work())

    def _on_prev(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        async def _work() -> None:
            await asyncio.to_thread(self._bot.spotify.previous_track)
            await self._bot.update_status_data()

        self._schedule(_work())

    def _on_mute(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        async def _work() -> None:
            muted = await asyncio.to_thread(self._bot.vm.toggle_mute)
            await self._bot.update_status_data(muted=muted)

        self._schedule(_work())

    def _on_vol_up(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        async def _work() -> None:
            vol = await asyncio.to_thread(self._bot.vm.change_volume, 2.0)
            await self._bot.update_status_data(volume=vol)

        self._schedule(_work())

    def _on_vol_down(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        async def _work() -> None:
            vol = await asyncio.to_thread(self._bot.vm.change_volume, -2.0)
            await self._bot.update_status_data(volume=vol)

        self._schedule(_work())

    def _on_export(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        """Launch exporter.py in its own Windows Terminal window for live progress."""

        env_guild_id = os.environ.get("DISCORD_SERVER_FOR_EXPORT_ID", "").strip()

        if not env_guild_id or not env_guild_id.isdigit():
            print("[tray] Export error: DISCORD_SERVER_FOR_EXPORT_ID is not assign, check .env")
            return

        guild_id = int(env_guild_id)

        exporter_path = BASE_DIR / "exporter.py"
        python_exe = sys.executable

        wt_path = shutil.which("wt") or shutil.which("wt.exe")
        if not wt_path:
            print(
                "[tray] Windows Terminal (wt.exe) не найден в PATH — "
                "открываю обычную консоль вместо него."
            )
            try:
                subprocess.Popen(
                    [python_exe, str(exporter_path), str(guild_id)],
                    cwd=str(project_dir),
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
            except Exception as exc:
                print(f"[tray] Не удалось запустить экспорт: {exc}")
            return

        try:
            subprocess.Popen(
                [
                    wt_path,
                    "-w",
                    "0",
                    "new-tab",
                    "--title",
                    "Discord Export",
                    "-d",
                    str(project_dir),
                    python_exe,
                    str(exporter_path),
                    str(guild_id),
                ],
                cwd=str(project_dir),
            )
        except Exception as exc:
            print(f"[tray] Не удалось запустить Windows Terminal: {exc}")

    @staticmethod
    def _on_exit(icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        try:
            icon.stop()
        except Exception:
            pass
        os._exit(0)

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("Обновить статус", self._on_refresh),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Медиа",
                pystray.Menu(
                    pystray.MenuItem("Пауза / Play", self._on_pause),
                    pystray.MenuItem("Следующий трек", self._on_skip),
                    pystray.MenuItem("Предыдущий трек", self._on_prev),
                    pystray.MenuItem("Mute Strip[7]", self._on_mute),
                    pystray.MenuItem("Громкость +2 dB", self._on_vol_up),
                    pystray.MenuItem("Громкость -2 dB", self._on_vol_down),
                ),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("📦 Экспорт сервера", self._on_export),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Авто-вход в VC",
                self._make_toggle("auto_join"),
                checked=self._is_checked("auto_join"),
            ),
            pystray.MenuItem(
                "Авто-выход из VC",
                self._make_toggle("auto_leave"),
                checked=self._is_checked("auto_leave"),
            ),
            pystray.MenuItem(
                "Доступ другим в VC",
                self._make_toggle("allow_others_vc"),
                checked=self._is_checked("allow_others_vc"),
            ),
            pystray.MenuItem(
                "Только владелец (команды)",
                self._make_toggle("only_owner_mode"),
                checked=self._is_checked("only_owner_mode"),
            ),
            pystray.MenuItem(
                "Живой статус (флаг)",
                self._make_toggle("status_enabled"),
                checked=self._is_checked("status_enabled"),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Выход", self._on_exit),
        )

    def start(self) -> None:
        image = load_tray_image()
        self._icon = pystray.Icon(
            "xd_discord_bot",
            image,
            "Discord Bot",
            self._build_menu(),
        )
        self._thread = threading.Thread(
            target=self._icon.run,
            name="system-tray",
            daemon=True,
        )
        self._thread.start()


def start_tray(bot: MusicBot, loop: asyncio.AbstractEventLoop) -> TrayApp:
    tray = TrayApp(bot, loop)
    tray.start()
    return tray
