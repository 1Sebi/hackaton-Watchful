"""/rooms — venue map landing endpoints + room activation.

The dashboard map shows one tile per room (not per camera) with a last-known
people count and an "active" flag. Selecting a room makes all its cameras the
AI-analyzed set (batched detection); leaving the map view is implicit (room
stays selected until another is picked).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.camera_manager import get_manager

router = APIRouter(prefix="/rooms", tags=["rooms"])


class ActivateBody(BaseModel):
    primary_cam: Optional[str] = None


@router.get("")
def list_rooms():
    """One entry per room: id, name, camera ids, current person count, active flag."""
    return get_manager().rooms_state()


@router.post("/{room_id}/activate")
def activate_room(room_id: str, body: Optional[ActivateBody] = None):
    """Make ``room_id`` the active room: all its cameras run batched detection.

    Optional ``primary_cam`` picks which camera inside the room is the editing
    focus (zones/conditions panels bind to it).
    """
    primary = body.primary_cam if body else None
    if not get_manager().set_active_room(room_id, primary_cam=primary):
        raise HTTPException(status_code=404, detail="room not found")
    return get_manager().rooms_state()
