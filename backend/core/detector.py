"""PersonDetector — YOLOv8 person detection + tracking.

Wraps Ultralytics ``model.track`` (ByteTrack) restricted to the COCO ``person``
class (id 0) and returns a clean ``List[Detection]`` the rest of the agent loop
can consume without touching Ultralytics internals.

On CPU use ``yolov8n.pt`` (~31 FPS); ``yolov8m.pt`` is ~2 FPS on CPU.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
from ultralytics import YOLO


def _env(key: str, default: str) -> str:
    v = os.environ.get(key)
    return v if v else default


@dataclass
class Detection:
    """One detected person in a frame."""

    track_id: Optional[int]
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2 (pixels)
    conf: float
    cls: int = 0  # COCO person

    @property
    def center(self) -> Tuple[int, int]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    @property
    def width(self) -> int:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]

    @property
    def area(self) -> int:
        return self.width * self.height


class PersonDetector:
    def __init__(
        self,
        model_path: Optional[str] = None,
        conf: Optional[float] = None,
        tracker: str = "bytetrack.yaml",
    ) -> None:
        self.model_path = model_path or _env("DETECTION_MODEL", "yolov8n.pt")
        self.conf = float(conf if conf is not None else _env("DETECTION_CONFIDENCE", "0.5"))
        self.tracker = tracker
        self.model = YOLO(self.model_path)

    # ── parsing ──────────────────────────────────────────────────────────
    @staticmethod
    def _boxes_to_detections(result) -> List[Detection]:
        dets: List[Detection] = []
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return dets
        for b in boxes:
            x1, y1, x2, y2 = (int(v) for v in b.xyxy[0].tolist())
            tid = int(b.id[0]) if b.id is not None else None
            conf = float(b.conf[0]) if b.conf is not None else 0.0
            dets.append(Detection(track_id=tid, bbox=(x1, y1, x2, y2), conf=conf))
        return dets

    # ── public API ───────────────────────────────────────────────────────
    def detect_and_track(self, frame: np.ndarray) -> List[Detection]:
        """Detect + track persons; ``Detection.track_id`` is a stable ByteTrack id."""
        results = self.model.track(
            frame,
            persist=True,
            classes=[0],
            conf=self.conf,
            verbose=False,
            tracker=self.tracker,
        )
        if not results:
            return []
        return self._boxes_to_detections(results[0])

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """Plain detection (no tracking); ``track_id`` is ``None``."""
        results = self.model.predict(frame, classes=[0], conf=self.conf, verbose=False)
        if not results:
            return []
        return self._boxes_to_detections(results[0])
