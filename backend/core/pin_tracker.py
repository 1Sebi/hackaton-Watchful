"""PinSession — record one pinned person's path as an annotated MP4.

When the user clicks a detected person in the live view, the focus camera's detect
loop starts feeding that person's frames here. Each cycle we draw the live box, the
trajectory so far (from the Track's position history), and a REC banner, then append
the frame to an MP4. On stop, the clip is finalized and sent to Telegram.

Single-camera by design: ids are per-camera (greedy-IoU), so a pin follows a person
within the focus camera. Cross-camera re-identification is out of scope.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from backend.core.detector import Detection
from backend.core.tracker import Track

# clips land here (gitignored); kept on disk so they can be re-sent / inspected
RECORD_DIR = Path(__file__).resolve().parents[2] / "recordings"
REC_WIDTH = 960          # standardize clip width (downscale 4K -> light mp4)
REC_FPS = 8.0            # nominal playback fps (detect cadence is ~5-8/s)

_TRAIL = (0, 220, 255)   # BGR yellow — the path
_BOX = (40, 80, 255)     # BGR red-orange — the pinned box
_WHITE = (255, 255, 255)


def draw_pinned(frame: np.ndarray, det: Detection, track: Optional[Track],
                elapsed: float, cam_name: str = "") -> np.ndarray:
    """Annotate a frame: trajectory polyline + highlighted box + REC banner."""
    img = frame.copy()
    # trajectory so far (Track keeps up to 64 recent centroids)
    if track is not None and len(track.positions) >= 2:
        pts = np.array(list(track.positions), dtype=np.int32)
        cv2.polylines(img, [pts], False, _TRAIL, 2, cv2.LINE_AA)
        for p in list(track.positions)[::3]:
            cv2.circle(img, (int(p[0]), int(p[1])), 2, _TRAIL, -1)

    x1, y1, x2, y2 = det.bbox
    cv2.rectangle(img, (x1, y1), (x2, y2), _BOX, 3)
    label = f"PINNED #{det.track_id}  {elapsed:.0f}s"
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    cv2.rectangle(img, (x1, max(0, y1 - th - 8)), (x1 + tw + 8, y1), _BOX, -1)
    cv2.putText(img, label, (x1 + 4, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, _WHITE, 1, cv2.LINE_AA)

    # REC banner
    cv2.circle(img, (22, 24), 7, (0, 0, 255), -1)
    head = f"REC  {cam_name}".strip()
    cv2.putText(img, head, (36, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, _WHITE, 2, cv2.LINE_AA)
    return img


class PinSession:
    def __init__(self, camera_id: str, camera_name: str, track_id: int) -> None:
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.track_id = track_id
        self.started = time.time()
        self.frames = 0
        self.last_seen = self.started
        self.path: Optional[str] = None
        self.lock = threading.Lock()
        self._writer: Optional[cv2.VideoWriter] = None
        self._size: Optional[Tuple[int, int]] = None
        self._trajectory: List[Tuple[int, int]] = []

    # ── recording (called from the detect-loop thread, under self.lock) ──
    def _ensure_writer(self, w: int, h: int) -> None:
        if self._writer is None:
            RECORD_DIR.mkdir(parents=True, exist_ok=True)
            fname = f"pin_{self.camera_id}_{self.track_id}_{int(self.started)}.mp4"
            self.path = str(RECORD_DIR / fname)
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self._writer = cv2.VideoWriter(self.path, fourcc, REC_FPS, (w, h))
            self._size = (w, h)

    def record(self, frame: np.ndarray, det: Detection, track: Optional[Track], now: float) -> None:
        ann = draw_pinned(frame, det, track, now - self.started, self.camera_name)
        h0, w0 = ann.shape[:2]
        scale = REC_WIDTH / float(w0)
        w, h = REC_WIDTH, int(round(h0 * scale))
        if h % 2:  # mp4 wants even dims
            h += 1
        ann = cv2.resize(ann, (w, h))
        self._ensure_writer(w, h)
        if self._size != (w, h):  # keep all frames the writer's size
            ann = cv2.resize(ann, self._size)
        self._writer.write(ann)
        self.frames += 1
        self.last_seen = now
        if track is not None and track.center:
            self._trajectory.append(track.center)

    def finalize(self) -> dict:
        if self._writer is not None:
            self._writer.release()
            self._writer = None
        duration = round(time.time() - self.started, 1)
        ok = bool(self.path and os.path.exists(self.path) and self.frames > 0)
        return {
            "ok": ok,
            "path": self.path,
            "frames": self.frames,
            "duration": duration,
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
            "track_id": self.track_id,
        }

    def status(self) -> dict:
        return {
            "pinned": True,
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
            "track_id": self.track_id,
            "frames": self.frames,
            "duration": round(time.time() - self.started, 1),
        }
