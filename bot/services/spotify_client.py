"""Spotify window discovery and media commands via Win32."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import psutil
import win32gui
import win32process

from bot.config import (
    MEDIA_NEXT,
    MEDIA_PLAY_PAUSE,
    MEDIA_PREV,
    SPOTIFY_IDLE_TITLES,
    WM_APPCOMMAND,
)


@dataclass(frozen=True, slots=True)
class SpotifyTrackInfo:
    title: str
    active: bool


class SpotifyClient:
    """Controls Spotify desktop client through its main window handle."""

    def __init__(self) -> None:
        self._hwnd_cache: int | None = None

    @staticmethod
    def _is_spotify_process(pid: int) -> bool:
        try:
            return psutil.Process(pid).name().lower() == "spotify.exe"
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def _find_main_window(self) -> int | None:
        hwnd = win32gui.FindWindow("SpotifyMainWindow", None)
        if hwnd:
            return hwnd

        found: list[int] = []

        def callback(hwnd: int, _: object) -> bool:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if not self._is_spotify_process(pid):
                return True
            title = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)
            if title or class_name == "Chrome_WidgetWin_0":
                found.append(hwnd)
                return False
            return True

        try:
            win32gui.EnumWindows(callback, None)
        except Exception:
            pass
        return found[0] if found else None

    def get_hwnd(self, *, refresh: bool = False) -> int | None:
        if refresh or self._hwnd_cache is None:
            self._hwnd_cache = self._find_main_window()
        elif self._hwnd_cache and not win32gui.IsWindow(self._hwnd_cache):
            self._hwnd_cache = self._find_main_window()
        return self._hwnd_cache

    def _post_command(self, command_code: int) -> bool:
        hwnd = self.get_hwnd(refresh=True)
        if not hwnd:
            return False
        win32gui.PostMessage(hwnd, WM_APPCOMMAND, 0, command_code)
        return True

    def play_pause(self) -> bool:
        return self._post_command(MEDIA_PLAY_PAUSE)

    def next_track(self) -> bool:
        return self._post_command(MEDIA_NEXT)

    def previous_track(self) -> bool:
        return self._post_command(MEDIA_PREV)

    def previous_track_twice(self) -> bool:
        if not self.previous_track():
            return False
        import time

        time.sleep(0.2)
        return self.previous_track()

    @staticmethod
    def _title_from_hwnd(hwnd: int) -> SpotifyTrackInfo:
        title = win32gui.GetWindowText(hwnd).strip()
        if title and title not in SPOTIFY_IDLE_TITLES:
            return SpotifyTrackInfo(title=title, active=True)
        return SpotifyTrackInfo(title="Idle", active=False)

    def get_track_info(self) -> SpotifyTrackInfo:
        hwnd = self.get_hwnd(refresh=True)
        if hwnd:
            return self._title_from_hwnd(hwnd)

        info = SpotifyTrackInfo(title="Idle", active=False)

        def callback(hwnd: int, _: object) -> bool:
            nonlocal info
            if not win32gui.IsWindowVisible(hwnd):
                return True
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if not self._is_spotify_process(pid):
                return True
            candidate = self._title_from_hwnd(hwnd)
            if candidate.active:
                info = candidate
                return False
            return True

        try:
            win32gui.EnumWindows(callback, None)
        except Exception:
            pass
        return info

    def parse_external_title(self, title: str | None) -> SpotifyTrackInfo | None:
        if not title:
            return None
        cleaned = title.strip()
        if not cleaned or cleaned in SPOTIFY_IDLE_TITLES:
            return SpotifyTrackInfo(title="Idle", active=False)
        return SpotifyTrackInfo(title=cleaned, active=True)
