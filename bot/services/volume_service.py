from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from bot.config import (
    FADE_MAX_STEPS,
    FADE_STEP_DB,
    FADE_STEP_DELAY_SECONDS,
)

if TYPE_CHECKING:
    from bot.bot import MusicBot


class VolumeService:

    def __init__(self, bot: MusicBot) -> None:
        self.bot = bot

    async def fade(self, target_v: float) -> float:
        current = await asyncio.to_thread(self.bot.vm.get_volume)
        steps = (
            int(abs(target_v - current) / FADE_STEP_DB) if FADE_STEP_DB else 1
        )
        steps = max(1, min(steps, FADE_MAX_STEPS))
        delta = (target_v - current) / steps
        value = current
        for _ in range(steps):
            value += delta
            await asyncio.to_thread(self.bot.vm.set_volume, value)
            await asyncio.sleep(FADE_STEP_DELAY_SECONDS)
        return await asyncio.to_thread(self.bot.vm.set_volume, target_v)

    async def set_volume(self, target_v: float) -> float:
        new_v = await self.fade(target_v)
        await self.bot.presence.update_status_data(volume=new_v)
        return new_v

    async def toggle_mute(self) -> bool:
        muted = await asyncio.to_thread(self.bot.vm.toggle_mute)
        await self.bot.presence.update_status_data(muted=muted)
        return muted