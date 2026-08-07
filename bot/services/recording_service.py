"""Автозапись голоса из VC — отдельный синхронизированный .wav на каждого.

Без команд: запись стартует и останавливается сама вместе с
подключением/отключением бота от голосового канала (см. bot/events/voice.py).

Синхронизация — по времени прихода пакета боту (time.perf_counter()), а не
по RTP-таймстемпам: RTP-часы разных участников не связаны друг с другом
(у каждого свой случайный старт), а момент получения пакета ботом — общий
для всех дорожек. Каждый sink перед записью реального аудио добивает файл
тишиной до позиции "прошло N секунд с начала сессии", поэтому сэмпл 0 во
всех файлах = один и тот же момент времени, и дальше они не расходятся.
"""

from __future__ import annotations

import traceback

import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import discord
from discord.ext import voice_recv

from bot.config import EXPORT_ROOT

if TYPE_CHECKING:
    from bot.bot import MusicBot

RECORDINGS_DIR: Path = EXPORT_ROOT / "recordings"


def _safe_name(user: Optional[discord.abc.User]) -> str:
    if user is None:
        return "unknown"
    raw = f"{user.id}_{getattr(user, 'name', 'unknown')}"
    return "".join(c for c in raw if c.isalnum() or c in ("_", "-"))


class SyncedWaveSink(voice_recv.WaveSink):
    BYTES_PER_SECOND = (
        voice_recv.WaveSink.SAMPLING_RATE
        * voice_recv.WaveSink.CHANNELS
        * voice_recv.WaveSink.SAMPLE_WIDTH
    )

    FRAME_SIZE = (
        voice_recv.WaveSink.CHANNELS
        * voice_recv.WaveSink.SAMPLE_WIDTH
    )

    def __init__(self, destination: str, session_start: float):
        super().__init__(destination)
        self._session_start = session_start
        self._bytes_written = 0

    def write(self, user, data):
        print(user, len(data.pcm))
        self._sink_for(user).write(user, data)

        pcm = data.pcm
        if not pcm:
            return

        expected = int(
            (time.perf_counter() - self._session_start)
            * self.BYTES_PER_SECOND
        )
        expected -= expected % self.FRAME_SIZE

        if expected > self._bytes_written:
            silence = expected - self._bytes_written
            self._file.writeframesraw(b"\x00" * silence)
            self._bytes_written += silence

        self._file.writeframesraw(pcm)
        self._bytes_written += len(pcm)


class PerUserSink(voice_recv.AudioSink):
    """Раздаёт входящее аудио по отдельному синхронизированному .wav на каждого."""

    def __init__(self, out_dir: Path, session_start: float) -> None:
        super().__init__()
        self._out_dir = out_dir
        self._session_start = session_start
        self._sinks: dict[int, SyncedWaveSink] = {}

    def wants_opus(self) -> bool:
        return False

    def _sink_for(self, user: Optional[discord.abc.User]) -> SyncedWaveSink:
        user_id = user.id if user else 0
        sink = self._sinks.get(user_id)
        if sink is None:
            path = self._out_dir / f"{_safe_name(user)}.wav"
            sink = SyncedWaveSink(str(path), self._session_start)
            self._sinks[user_id] = sink
        return sink

    def write(self, user, data) -> None:
        self._sink_for(user).write(user, data)

    def cleanup(self) -> None:
        for sink in self._sinks.values():
            try:
                sink.cleanup()
            except Exception as exc:
                print(f"[recording] sink cleanup error: {exc}")
        self._sinks.clear()


class RecordingService:
    def __init__(self, bot: MusicBot) -> None:
        self.bot = bot
        self._sink: PerUserSink | None = None
        self._session_dir: Path | None = None

    @property
    def is_recording(self) -> bool:
        return self._sink is not None

    def start(self, guild: discord.Guild) -> Path | None:
        if self.is_recording:
            return self._session_dir

        vc = guild.voice_client
        if not isinstance(vc, voice_recv.VoiceRecvClient):
            print("[recording] voice client не VoiceRecvClient — запись пропущена")
            return None

        session_start = time.perf_counter()
        session_dir = RECORDINGS_DIR / f"{guild.id}_{int(time.time())}"
        session_dir.mkdir(parents=True, exist_ok=True)

        self._sink = PerUserSink(session_dir, session_start)
        self._session_dir = session_dir

        if vc.is_listening():
            vc.stop_listening()

        vc.listen(self._sink)
        print(f"[recording] авто-запись начата: {session_dir}")
        return session_dir

    def stop(self, guild: discord.Guild) -> Path | None:
        print("Stop called")
        traceback.print_stack(limit=10)
        vc = guild.voice_client
        if isinstance(vc, voice_recv.VoiceRecvClient) and vc.is_listening():
            vc.stop_listening()

        finished_dir = self._session_dir
        print(f"[recording] запись остановлена: {finished_dir}")
        self._sink = None
        self._session_dir = None
        return finished_dir
    