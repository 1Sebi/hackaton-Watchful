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
            # all room cameras (not just the focused one). Override persons +
            # rules with the aggregate so StatusBar / overlays show the right
            # picture regardless of which camera the user is editing.
            room_cams = mgr.cams_in_room(mgr.active_room_id)
            if room_cams:
                total = 0
                rules = 0
                known = False
                for w in room_cams:
                    v = w.tracker.active_count if w.is_active else w.tile_persons
                    if v is not None:
                        total += int(v)
                        known = True
                    rules += len([c for c in w._conditions if c["enabled"]])
                if known:
                    payload["persons"] = total
                payload["conditions"] = rules
                payload["room_detect_fps"] = mgr.room_detect_fps
            await ws.send_json(payload)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return
    except Exception:
        return
