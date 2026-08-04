"""FastAPI bridge: AutoHotkey hotkeys -> instant Discord status updates."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel

from config import WEB_HOST, WEB_PORT, BRIDGE_TOKEN
from voicemeeter_client import VoicemeeterClient

if TYPE_CHECKING:
    from bot_instance import MusicBot


class VolumePayload(BaseModel):
    delta: float | None = None
    volume: float | None = None


class TrackHintPayload(BaseModel):
    track_title: str | None = None
    track_active: bool | None = None


class StatusPayload(TrackHintPayload):
    volume: float | None = None
    muted: bool | None = None

def _check_bridge_token(request: Request) -> None:
    if not BRIDGE_TOKEN:
        return
    if request.headers.get("X-Bridge-Token") != BRIDGE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid bridge token")

def create_app(vm: VoicemeeterClient) -> FastAPI:
    app = FastAPI(
        title="DiscordBot AHK Bridge", 
        docs_url=None, 
        redoc_url=None,
        dependencies=[Depends(_check_bridge_token)])
    app.state.bot = None  # type: MusicBot | None
    app.state.vm = vm

    def _bot(request: Request) -> MusicBot:
        bot = request.app.state.bot
        if bot is None:
            raise HTTPException(status_code=503, detail="Discord bot is not ready")
        return bot

    async def _push_status(
        request: Request,
        payload: StatusPayload | None = None,
        *,
        refresh_track: bool = True,
    ) -> dict[str, Any]:
        bot = _bot(request)
        kwargs: dict[str, Any] = {}
        if payload:
            if payload.volume is not None:
                kwargs["volume"] = payload.volume
            if payload.muted is not None:
                kwargs["muted"] = payload.muted
            if payload.track_title is not None:
                kwargs["track_title"] = payload.track_title
            if payload.track_active is not None:
                kwargs["track_active"] = payload.track_active
        await bot.update_status_data(refresh_track=refresh_track, **kwargs)
        state = bot.get_live_state()
        return {
            "ok": True,
            "volume": state.volume_db,
            "muted": state.muted,
            "track_title": state.track_title,
            "track_active": state.track_active,
        }

    @app.get("/health")
    async def health(request: Request) -> dict[str, str]:
        ready = request.app.state.bot is not None
        return {"status": "ok" if ready else "starting"}

    @app.get("/ahk/state")
    async def ahk_state(request: Request) -> dict[str, Any]:
        vm_client: VoicemeeterClient = request.app.state.vm
        if not vm_client.is_connected:
            raise HTTPException(status_code=503, detail="Voicemeeter unavailable")
        state = await asyncio.to_thread(vm_client.get_state)
        track = None
        if request.app.state.bot is not None:
            track = request.app.state.bot.spotify.get_track_info()
        return {
            "volume": state.volume_db,
            "muted": state.muted,
            "track_title": track.title if track else "Idle",
            "track_active": track.active if track else False,
        }

    @app.post("/ahk/volume_changed")
    async def volume_changed(request: Request, body: VolumePayload) -> dict[str, Any]:
        vm_client: VoicemeeterClient = request.app.state.vm
        if not vm_client.is_connected:
            raise HTTPException(status_code=503, detail="Voicemeeter unavailable")

        if body.volume is not None:
            new_vol = await asyncio.to_thread(vm_client.set_volume, body.volume)
        elif body.delta is not None:
            new_vol = await asyncio.to_thread(vm_client.change_volume, body.delta)
        else:
            raise HTTPException(status_code=400, detail="Provide delta or volume")

        return await _push_status(
            request,
            StatusPayload(volume=new_vol),
            refresh_track=False,
        )

    @app.post("/ahk/mute_toggle")
    async def mute_toggle(request: Request) -> dict[str, Any]:
        vm_client: VoicemeeterClient = request.app.state.vm
        if not vm_client.is_connected:
            raise HTTPException(status_code=503, detail="Voicemeeter unavailable")
        muted = await asyncio.to_thread(vm_client.toggle_mute)
        return await _push_status(
            request, StatusPayload(muted=muted), refresh_track=False
        )

    @app.post("/ahk/play_pause")
    async def play_pause(request: Request, body: TrackHintPayload) -> dict[str, Any]:
        return await _push_status(request, StatusPayload(**body.model_dump()))

    @app.post("/ahk/track_skipped")
    async def track_skipped(request: Request, body: TrackHintPayload) -> dict[str, Any]:
        return await _push_status(request, StatusPayload(**body.model_dump()))

    @app.post("/ahk/track_prev")
    async def track_prev(request: Request, body: TrackHintPayload) -> dict[str, Any]:
        return await _push_status(request, StatusPayload(**body.model_dump()))

    @app.post("/ahk/spotify_restarted")
    async def spotify_restarted(
        request: Request, body: TrackHintPayload
    ) -> dict[str, Any]:
        return await _push_status(request, StatusPayload(**body.model_dump()))

    @app.post("/ahk/status_refresh")
    async def status_refresh(request: Request) -> dict[str, Any]:
        return await _push_status(request, refresh_track=True)

    @app.post("/ahk/presence_notify")
    async def presence_notify(
        request: Request, body: StatusPayload = StatusPayload()
    ) -> dict[str, Any]:
        """Update Discord presence only (AHK already changed VM/Spotify locally)."""
        if request.app.state.bot is None:
            return {"ok": False, "reason": "bot_not_ready"}
        return await _push_status(
            request,
            body,
            refresh_track=body.track_title is None,
        )

    return app


def bind_bot(app: FastAPI, bot: MusicBot) -> None:
    app.state.bot = bot


async def serve_web(app: FastAPI, host: str = WEB_HOST, port: int = WEB_PORT) -> None:
    import uvicorn

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        loop="asyncio",
        access_log=False,
    )
    server = uvicorn.Server(config)
    await server.serve()
