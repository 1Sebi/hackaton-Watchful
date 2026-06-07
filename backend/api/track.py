"""/track — pin a detected person, record their path, send the clip to Telegram.

Flow: the live-view overlay polls GET /track/detections to draw clickable boxes;
clicking one POSTs /track/pin with its track_id; the focus camera's detect loop then
records an annotated clip; POST /track/stop finalizes it and pushes it to Telegram.
Routes are sync (def) so the blocking Telegram upload runs in FastAPI's threadpool.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from backend.core.camera_manager import get_manager

router = APIRouter(prefix="/track", tags=["track"])


class PinIn(BaseModel):
    camera_id: str
    track_id: int


@router.get("/detections")
def detections(camera_id: Optional[str] = None):
    """Per-person boxes for the focus (or given) camera, for the click overlay."""
    return get_manager().detections_for(camera_id)


@router.get("/status")
def status():
    return get_manager().pin_status()


@router.post("/pin")
def pin(body: PinIn):
    return get_manager().pin_start(body.camera_id, body.track_id)


@router.post("/stop")
def stop():
    """Finalize the recording and send it to Telegram. May take a few seconds."""
    return get_manager().pin_stop()
