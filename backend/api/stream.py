"""/stream — MJPEG live view with overlays + single-frame snapshot."""
from __future__ import annotations

import time

from fastapi import APIRouter
from fastapi.responses import Response, StreamingResponse

from backend.core.pipeline import get_pipeline

router = APIRouter(tags=["stream"])


def _mjpeg_generator():
    pl = get_pipeline()
    while True:
        jpg = pl.latest_jpeg
        if jpg:
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n"
                   b"Content-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
        time.sleep(0.04)  # ~25 fps cap


@router.get("/stream/live.mjpg")
def live():
    return StreamingResponse(_mjpeg_generator(),
                             media_type="multipart/x-mixed-replace; boundary=frame")


@router.get("/stream/snapshot.jpg")
def snapshot():
    jpg = get_pipeline().latest_jpeg
    if not jpg:
        return Response(status_code=503, content=b"no frame yet")
    return Response(content=jpg, media_type="image/jpeg")
