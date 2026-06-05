"""ReferenceFrame + AdaptiveSampler — skip expensive VLM calls on a static scene.

Keeps a blurred grayscale "background" reference and reports when the current
frame differs enough to be worth a semantic VLM check. A stable scene auto-
refreshes the reference (every ``update_interval`` seconds) so gradual lighting
drift isn't mistaken for activity. This is the cost-zero lever from the brief:
no scene change -> no VLM call.
"""
from __future__ import annotations

import time
from typing import Optional

import cv2
import numpy as np


class ReferenceFrame:
    def __init__(
        self,
        min_changed_pct: float = 1.5,
        pixel_delta: int = 25,
        update_interval: float = 300.0,
        blur: int = 21,
    ) -> None:
        self.min_changed_pct = min_changed_pct  # % of pixels that must differ
        self.pixel_delta = pixel_delta          # per-pixel intensity delta to count
        self.update_interval = update_interval  # auto-refresh reference (seconds)
        self.blur = blur
        self._ref: Optional[np.ndarray] = None
        self.last_update: float = 0.0

    def _prep(self, frame: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(gray, (self.blur, self.blur), 0)

    def update(self, frame: np.ndarray, now: Optional[float] = None) -> None:
        self._ref = self._prep(frame)
        self.last_update = time.time() if now is None else now

    def changed_pct(self, frame: np.ndarray) -> float:
        cur = self._prep(frame)
        if self._ref is None or self._ref.shape != cur.shape:
            return 100.0
        diff = cv2.absdiff(self._ref, cur)
        changed = int(np.count_nonzero(diff > self.pixel_delta))
        return 100.0 * changed / diff.size

    def significant_change(self, frame: np.ndarray, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        if self._ref is None:
            self.update(frame, now)
            return True
        changed = self.changed_pct(frame) >= self.min_changed_pct
        # learn a stable background after the scene has been quiet for a while
        if not changed and (now - self.last_update) > self.update_interval:
            self.update(frame, now)
        return changed


class AdaptiveSampler:
    """Gate VLM calls on scene change, with a periodic forced check."""

    def __init__(self, reference: Optional[ReferenceFrame] = None, force_interval: float = 30.0) -> None:
        self.reference = reference or ReferenceFrame()
        self.force_interval = force_interval  # run VLM at least this often even if static
        self.last_vlm: float = -1e18

    def should_run_vlm(self, frame: np.ndarray, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        changed = self.reference.significant_change(frame, now)
        forced = (now - self.last_vlm) >= self.force_interval
        run = changed or forced
        if run:
            self.last_vlm = now
        return run
