"""/stream — per-camera MJPEG live view with overlays + single-frame snapshot.

``/stream/{camera_id}/live.mjpg`` streams a specific grid camera; the bare
``/stream/live.mjpg`` follows whichever camera is currently AI-active.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse

from backend.core.camera_manager import get_manager

router = APIRouter(tags=["stream"])


def _frames(get_worker):
    """MJPEG multipart generator that re-reads the worker each tick (so the bare
    alias follows the active camera, and a per-camera stream keeps flowing)."""
    while True:
        w = get_worker()
        jpg = w.latest_jpeg if w is not None else None
        if jpg:
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n"
                   b"Content-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
        time.sleep(0.04)  # ~25 fps cap


@router.get("/stream/{camera_id}/live.mjpg")
def live_camera(camera_id: str):
    mgr = get_manager()
    if mgr.get(camera_id) is None:
        raise HTTPException(status_code=404, detail="camera not found")
    return StreamingResponse(_frames(lambda: mgr.get(camera_id)),
                             media_type="multipart/x-mixed-replace; boundary=frame")


@router.get("/stream/{camera_id}/snapshot.jpg")
def snapshot_camera(camera_id: str):
    w = get_manager().get(camera_id)
    if w is None:
        raise HTTPException(status_code=404, detail="camera not found")
    if not w.latest_jpeg:
        return Response(status_code=503, content=b"no frame yet")
    return Response(content=w.latest_jpeg, media_type="image/jpeg")


@router.get("/stream/live.mjpg")
def live():
    """Alias: follow the active camera."""
    mgr = get_manager()
    return StreamingResponse(_frames(mgr.active),
                             media_type="multipart/x-mixed-replace; boundary=frame")


@router.get("/stream/snapshot.jpg")
def snapshot():
    w = get_manager().active()
    if w is None or not w.latest_jpeg:
        return Response(status_code=503, content=b"no frame yet")
    return Response(content=w.latest_jpeg, media_type="image/jpeg")
