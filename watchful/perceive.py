"""Perceive — pull frames from the Hikvision RTSP stream and gate on motion.

The motion gate is the cheap pre-filter: only spend a VLM call when the scene
actually changed. This is the single biggest lever for both speed and cost.
"""
from __future__ import annotations

import time

import cv2
import numpy as np

from .config import CameraConfig


class FrameSource:
    def __init__(self, camera: CameraConfig, reconnect_delay: float = 2.0):
        self.camera = camera
        self.reconnect_delay = reconnect_delay
        self._cap: cv2.VideoCapture | None = None
        self._prev_gray: np.ndarray | None = None

    def open(self) -> None:
        self._cap = cv2.VideoCapture(self.camera.rtsp_url, cv2.CAP_FFMPEG)
        # Keep buffer tiny so read() returns a *fresh* frame, not a stale queued one.
        try:
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        if not self._cap.isOpened():
            raise RuntimeError(
                f"Could not open RTSP stream. Check creds/IP/channel.\n  {self.camera.rtsp_url}"
            )

    def read(self) -> np.ndarray | None:
        """Return the latest frame, reconnecting on transient failures."""
        if self._cap is None:
            self.open()
        ok, frame = self._cap.read()
        if not ok or frame is None:
            # transient drop -> reconnect
            self._cap.release()
            time.sleep(self.reconnect_delay)
            self.open()
            ok, frame = self._cap.read()
            if not ok:
                return None
        return frame

    def motion_changed(self, frame: np.ndarray, threshold: float = 1.5) -> bool:
        """True if enough pixels changed vs the previous frame.

        threshold = % of pixels that must differ. First frame always passes.
        Tune higher to ignore lighting flicker; lower to catch subtle motion.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        if self._prev_gray is None:
            self._prev_gray = gray
            return True
        delta = cv2.absdiff(self._prev_gray, gray)
        _, mask = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)
        changed_pct = 100.0 * np.count_nonzero(mask) / mask.size
        self._prev_gray = gray
        return changed_pct >= threshold

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
