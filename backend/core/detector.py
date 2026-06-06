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
        self.model_path = model_path or _env("DETECTION_MODEL", "yolov8m.pt")
        self.conf = float(conf if conf is not None else _env("DETECTION_CONFIDENCE", "0.25"))
        # NMS IoU — Ultralytics default 0.7 is too aggressive for dense rooms
        # (two people standing close share a lot of bbox area and one gets
        # suppressed). 0.5 keeps overlapping persons distinct.
        self.iou = float(_env("DETECTION_IOU", "0.5"))
        # Inference letterbox size. Larger = small/distant people keep enough
        # pixels to be detected (the dominant recall lever on wide overhead
        # shots). Must be a multiple of 32. 640 = YOLO default; 960 recommended.
        self.imgsz = int(_env("DETECTION_IMGSZ", "960"))
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
            iou=self.iou,
            imgsz=self.imgsz,
            verbose=False,
            tracker=self.tracker,
        )
        if not results:
            return []
        return self._boxes_to_detections(results[0])

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """Plain detection (no tracking); ``track_id`` is ``None``."""
        results = self.model.predict(
            frame, classes=[0], conf=self.conf, iou=self.iou, imgsz=self.imgsz, verbose=False
        )
        if not results:
            return []
        return self._boxes_to_detections(results[0])

    def detect_batch(self, frames: List[np.ndarray]) -> List[List[Detection]]:
        """Batched plain detection over N frames in a single model call.

        Ultralytics packs the frames into one inference pass (~1.5x cost for 4
        frames vs 4× separate calls on CPU), enabling realistic multi-camera
        detection on a CPU-only box. No tracking here — ByteTrack is per-stream
        and can't be batched. The caller (a per-camera TrackManager) associates
        these box-only detections with prior tracks via IoU.

        Returns one list of Detection per input frame, same order.
        """
        if not frames:
            return []
        results = self.model.predict(
            frames, classes=[0], conf=self.conf, iou=self.iou,
            imgsz=self.imgsz, verbose=False,
        )
        return [self._boxes_to_detections(r) for r in results]

    def reset_tracker(self) -> None:
        """Clear ByteTrack state — call when switching which camera is detected,
        so track ids from the previous scene don't bleed into the new one."""
        try:
            pred = getattr(self.model, "predictor", None)
            trackers = getattr(pred, "trackers", None) if pred is not None else None
            for t in trackers or []:
                if hasattr(t, "reset"):
                    t.reset()
        except Exception:
            pass
