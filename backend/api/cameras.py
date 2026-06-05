"""/cameras — list the venue grid and switch which camera the AI runs on."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.core.camera_manager import get_manager

router = APIRouter(prefix="/cameras", tags=["cameras"])


@router.get("")
def list_cameras():
    """All grid cameras with per-tile state (fps, persons, motion) + the active id."""
    return get_manager().cameras_state()


@router.post("/{camera_id}/activate")
def activate(camera_id: str):
    """Make ``camera_id`` the AI-active camera (full detection + its own rules)."""
    if not get_manager().set_active(camera_id):
        raise HTTPException(status_code=404, detail="camera not found")
    return get_manager().cameras_state()
