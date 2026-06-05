"""VideoSource — unified frame capture for webcam, RTSP, or video file.

Buffered at size 1 so ``read()`` always returns the freshest frame (no stale
queue), with bounded auto-reconnect for flaky RTSP streams. Usable as a context
manager. This is the single perception entry point for the whole agent loop.
"""
from __future__ import annotations

import os
import sys
import time
from typing import Optional, Union

# Harden RTSP transport: force TCP (not lossy UDP) + an 8s open/read timeout.
# Must be set BEFORE cv2 is imported so FFmpeg picks it up — prevents UDP
# artifacts ("PPS id out of range" on some HEVC cams) and infinite hangs on a
# dead stream. (Validated against the live ThePlace NVRs.)
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;8000000"
)

import cv2  # noqa: E402
import numpy as np  # noqa: E402


class VideoSource:
    """Wrap ``cv2.VideoCapture`` with a tiny buffer + reconnect logic.

    ``source`` may be:
      * ``int``  -> webcam index (e.g. ``0``)
      * ``str``  -> RTSP URL (``rtsp://...``) or a path to a video file
    """

    def __init__(
        self,
        source: Union[int, str] = 0,
        max_reconnect: int = 5,
        reconnect_delay: float = 1.5,
    ) -> None:
        self.source = self._coerce(source)
        self.max_reconnect = max_reconnect
        self.reconnect_delay = reconnect_delay
        self._cap: Optional[cv2.VideoCapture] = None
        self._reconnects = 0
        self.open()

    # ── helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _coerce(source: Union[int, str]) -> Union[int, str]:
        # "0" -> 0 (webcam index); keep rtsp:// URLs and file paths as str
        if isinstance(source, str) and source.isdigit():
            return int(source)
        return source

    @property
    def is_rtsp(self) -> bool:
        return isinstance(self.source, str) and self.source.lower().startswith("rtsp")

    @property
    def is_file(self) -> bool:
        return isinstance(self.source, str) and not self.is_rtsp

    def _backend(self) -> int:
        if isinstance(self.source, int):
            # Media Foundation delivers full 30 FPS @ 640x480 on Windows webcams;
            # DirectShow's auto-exposure caps delivery to ~10 FPS in indoor light.
            return cv2.CAP_MSMF if sys.platform == "win32" else cv2.CAP_ANY
        if self.is_rtsp:
            return cv2.CAP_FFMPEG  # RTSP over FFmpeg
        return cv2.CAP_ANY

    # ── lifecycle ────────────────────────────────────────────────────────
    def open(self) -> None:
        if self._cap is not None:
            self._cap.release()
        self._cap = cv2.VideoCapture(self.source, self._backend())
        if isinstance(self.source, int):
            # Webcams via DirectShow default to uncompressed YUY2 (~10 FPS @ 640x480).
            # Requesting MJPG unlocks the camera's high-FPS compressed mode.
            try:
                self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                self._cap.set(cv2.CAP_PROP_FPS, 30)
            except Exception:
                pass
        # tiny buffer -> read() yields the freshest frame, not a queued stale one
        try:
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        if not self._cap.isOpened():
            raise RuntimeError(f"VideoSource: could not open source {self.source!r}")
        if self.is_rtsp:
            # first ~3-5 frames are gray/partial until the decoder hits a keyframe
            for _ in range(5):
                self._cap.read()

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    # ── properties ───────────────────────────────────────────────────────
    @property
    def width(self) -> int:
        return int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if self._cap else 0

    @property
    def height(self) -> int:
        return int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if self._cap else 0

    @property
    def fps(self) -> float:
        fps = self._cap.get(cv2.CAP_PROP_FPS) if self._cap else 0.0
        # webcams/files sometimes report 0 or garbage -> normalise to 0.0
        return float(fps) if fps and fps > 0 else 0.0

    # ── frame access ─────────────────────────────────────────────────────
    def read(self) -> Optional[np.ndarray]:
        """Return the latest BGR frame, or ``None`` if exhausted/unrecoverable."""
        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        if ok and frame is not None:
            self._reconnects = 0
            return frame
        # transient failure (RTSP drop) -> bounded reconnect. For files, EOF.
        if self.is_file:
            return None
        return self._reconnect_and_read()

    def _reconnect_and_read(self) -> Optional[np.ndarray]:
        while self._reconnects < self.max_reconnect:
            self._reconnects += 1
            time.sleep(self.reconnect_delay)
            try:
                self.open()
            except RuntimeError:
                continue
            ok, frame = self._cap.read()
            if ok and frame is not None:
                return frame
        return None

    # ── context manager ──────────────────────────────────────────────────
    def __enter__(self) -> "VideoSource":
        return self

    def __exit__(self, *exc) -> None:
        self.release()

    def __repr__(self) -> str:
        return (
            f"VideoSource(source={self.source!r}, "
            f"{self.width}x{self.height}@{self.fps:.0f}fps)"
        )
