"""WebSocket endpoints — live events and live state."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core.pipeline import get_pipeline

router = APIRouter()


@router.websocket("/ws/events")
async def ws_events(ws: WebSocket):
    await ws.accept()
    pl = get_pipeline()
    last = pl._event_seq
    try:
        while True:
            for e in pl.events_since(last):
                last = e["seq"]
                await ws.send_json(e)
            await asyncio.sleep(0.3)
    except WebSocketDisconnect:
        return
    except Exception:
        return


@router.websocket("/ws/state")
async def ws_state(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            await ws.send_json(get_pipeline().state())
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return
    except Exception:
        return
