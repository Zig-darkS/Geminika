"""Entry point: Discord bot + FastAPI AHK bridge in one asyncio event loop."""

from __future__ import annotations

import argparse
import asyncio
import atexit
import sys

from bot.bot import create_bot
from bot.config import DISCORD_BOT_TOKEN, save_settings
from bot.ui.tray_app import start_tray
from bot.services.voicemeeter_client import VoicemeeterClient
from bot.web.web_server import bind_bot, create_app, serve_web


def hide_console_window() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except OSError:
        pass


async def main() -> None:
    loop = asyncio.get_running_loop()
    vm = VoicemeeterClient()
    bot = create_bot(vm)
    app = create_app(vm)
    bind_bot(app, bot)

    start_tray(bot, loop)

    atexit.register(save_settings)
    if vm.is_connected:
        atexit.register(vm.logout)

    async def run_discord() -> None:
        try:
            await bot.start(DISCORD_BOT_TOKEN)
        except asyncio.CancelledError:
            await bot.close()
            raise

    discord_task = asyncio.create_task(run_discord(), name="discord-bot")
    web_task = asyncio.create_task(serve_web(app), name="ahk-web-server")

    try:
        await asyncio.gather(discord_task, web_task)
    except KeyboardInterrupt:
        pass
    finally:
        for task in (discord_task, web_task):
            task.cancel()
        await asyncio.gather(discord_task, web_task, return_exceptions=True)
        save_settings()
        vm.logout()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Discord Bot + AHK bridge")
    parser.add_argument(
        "--console",
        action="store_true",
        help="Keep the console window visible (debug)",
    )
    args = parser.parse_args()

    if not DISCORD_BOT_TOKEN.strip():
        print(
            "Set DISCORD_TOKEN environment variable before starting main.py",
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.console:
        hide_console_window()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
