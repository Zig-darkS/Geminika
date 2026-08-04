"""Thread-safe Voicemeeter Remote API wrapper (ctypes)."""

from __future__ import annotations

import atexit
import ctypes
import threading
from dataclasses import dataclass
from typing import Final

from config import VM_DLL_PATH, VM_STRIP_INDEX

_GAIN_PARAM: Final[bytes] = f"Strip[{VM_STRIP_INDEX}].Gain".encode("ascii")
_MUTE_PARAM: Final[bytes] = f"Strip[{VM_STRIP_INDEX}].Mute".encode("ascii")
_MIN_DB: Final[float] = -60.0
_MAX_DB: Final[float] = 12.0


@dataclass(frozen=True, slots=True)
class VoicemeeterState:
    volume_db: float
    muted: bool


class VoicemeeterClient:
    """Synchronous, thread-safe wrapper around VoicemeeterRemote64.dll."""

    def __init__(self, dll_path: str | None = None) -> None:
        self._lock = threading.RLock()
        self._dll: ctypes.WinDLL | None = None
        self._path = dll_path or str(VM_DLL_PATH)
        self._connected = False
        self._connect()

    def _connect(self) -> None:
        if not VM_DLL_PATH.is_file():
            print(f"Voicemeeter DLL not found: {self._path}")
            return
        try:
            dll = ctypes.windll.LoadLibrary(self._path)
            result = dll.VBVMR_Login()
            if result < 0:
                print(f"Voicemeeter login failed with code {result}")
                return
            self._dll = dll
            self._connected = True
            atexit.register(self.logout)
        except OSError as exc:
            print(f"Voicemeeter DLL error: {exc}")

    @property
    def is_connected(self) -> bool:
        return self._connected and self._dll is not None

    def logout(self) -> None:
        with self._lock:
            if self._dll is not None:
                try:
                    self._dll.VBVMR_Logout()
                except OSError:
                    pass
                self._dll = None
                self._connected = False

    def _require_dll(self) -> ctypes.WinDLL:
        if not self.is_connected or self._dll is None:
            raise RuntimeError("Voicemeeter is not connected")
        return self._dll

    @staticmethod
    def _clamp_volume(value: float) -> float:
        return max(_MIN_DB, min(_MAX_DB, float(value)))

    def refresh_parameters(self) -> None:
        with self._lock:
            dll = self._require_dll()
            dll.VBVMR_IsParametersDirty()

    def get_volume(self) -> float:
        with self._lock:
            dll = self._require_dll()
            dll.VBVMR_IsParametersDirty()
            value = ctypes.c_float()
            dll.VBVMR_GetParameterFloat(_GAIN_PARAM, ctypes.byref(value))
            return float(value.value)

    def set_volume(self, value: float) -> float:
        clamped = self._clamp_volume(value)
        with self._lock:
            dll = self._require_dll()
            dll.VBVMR_IsParametersDirty()
            dll.VBVMR_SetParameterFloat(_GAIN_PARAM, ctypes.c_float(clamped))
        return clamped

    def change_volume(self, delta: float) -> float:
        current = self.get_volume()
        return self.set_volume(current + delta)

    def is_muted(self) -> bool:
        with self._lock:
            dll = self._require_dll()
            dll.VBVMR_IsParametersDirty()
            value = ctypes.c_float()
            dll.VBVMR_GetParameterFloat(_MUTE_PARAM, ctypes.byref(value))
            return value.value > 0.5

    def set_mute(self, muted: bool) -> bool:
        with self._lock:
            dll = self._require_dll()
            dll.VBVMR_IsParametersDirty()
            dll.VBVMR_SetParameterFloat(
                _MUTE_PARAM, ctypes.c_float(1.0 if muted else 0.0)
            )
        return muted

    def toggle_mute(self) -> bool:
        return self.set_mute(not self.is_muted())

    def get_state(self) -> VoicemeeterState:
        return VoicemeeterState(volume_db=self.get_volume(), muted=self.is_muted())
