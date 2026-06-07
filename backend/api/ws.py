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
            payload["active_room"] = grid.get("active_room")
            payload["cameras"] = grid["cameras"]
            # In room mode the meaningful HUD number is the total people across
            # all room cameras (not just the focused one). Every visible
            # camera runs full detection now, so tracker.active_count is the
            # honest live number for each — sum them.
            room_cams = mgr.cams_in_room(mgr.active_room_id)
            if room_cams:
                payload["persons"] = sum(w.tracker.active_count for w in room_cams)
                payload["conditions"] = sum(
                    len([c for c in w._conditions if c["enabled"]]) for w in room_cams
                )
            await ws.send_json(payload)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return
    except Exception:
        return
