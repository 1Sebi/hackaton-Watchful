"""WebSocket endpoints — live events and live state (multi-camera aware)."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core.camera_manager import get_manager

router = APIRouter()


@router.websocket("/ws/events")
async def ws_events(ws: WebSocket):
    await ws.accept()
    mgr = get_manager()
    seen: dict = {}  # worker_id -> last seq pushed
    try:
        while True:
            for w in mgr.workers.values():
                for e in w.events_since(seen.get(w.id, 0)):
                    seen[w.id] = e["seq"]
                    await ws.send_json(e)  # carries camera_id + camera_name
            await asyncio.sleep(0.3)
    except WebSocketDisconnect:
        return
    except Exception:
        return


@router.websocket("/ws/state")
async def ws_state(ws: WebSocket):
    await ws.accept()
    mgr = get_manager()
    try:
        while True:
            active = mgr.active()
            payload = active.state() if active is not None else {"running": False}
            grid = mgr.cameras_state()
            payload["active"] = grid["active"]
            payload["cameras"] = grid["cameras"]
            await ws.send_json(payload)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return
    except Exception:
        return
