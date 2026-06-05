"""PoseAnalyzer — YOLOv8-pose keypoints + geometric posture rules.

Detects 17 COCO keypoints per person and answers cheap, deterministic posture
questions (hand raised, sitting, standing) used by the "pose" predicate
evaluator. Any rule returns ``False`` when its required keypoints are missing or
low-confidence — we never guess. Poses are associated to tracked detections by
bbox IoU so a posture can be attributed to a specific person/track id.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from ultralytics import YOLO

from backend.core.detector import Detection


def _env(key: str, default: str) -> str:
    v = os.environ.get(key)
    return v if v else default


# COCO-17 keypoint order (Ultralytics pose output)
COCO_KEYPOINTS = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]
KP_INDEX = {name: i for i, name in enumerate(COCO_KEYPOINTS)}

# limb pairs for skeleton drawing
COCO_SKELETON: List[Tuple[int, int]] = [
    (5, 7), (7, 9), (6, 8), (8, 10), (5, 6), (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16), (0, 5), (0, 6), (0, 1), (0, 2),
    (1, 3), (2, 4),
]


@dataclass
class Keypoint:
    x: float
    y: float
    conf: float


@dataclass
class Pose:
    keypoints: np.ndarray  # shape (17, 3): x, y, conf
    bbox: Tuple[int, int, int, int]
    conf: float

    def kp(self, name: str) -> Keypoint:
        x, y, c = self.keypoints[KP_INDEX[name]]
        return Keypoint(float(x), float(y), float(c))


class PoseAnalyzer:
    def __init__(
        self,
        model_path: Optional[str] = None,
        conf: Optional[float] = None,
        kp_conf: float = 0.3,
    ) -> None:
        self.model_path = model_path or _env("POSE_MODEL", "yolov8n-pose.pt")
        self.conf = float(conf if conf is not None else _env("DETECTION_CONFIDENCE", "0.5"))
        self.kp_conf = kp_conf  # min keypoint confidence to trust a joint
        self.model = YOLO(self.model_path)

    # ── inference ────────────────────────────────────────────────────────
    def analyze(self, frame: np.ndarray) -> List[Pose]:
        results = self.model.predict(frame, conf=self.conf, verbose=False)
        poses: List[Pose] = []
        if not results:
            return poses
        r = results[0]
        if r.keypoints is None or r.boxes is None:
            return poses
        kp_data = r.keypoints.data.cpu().numpy()  # (N, 17, 3)
        boxes = r.boxes
        for i in range(len(kp_data)):
            x1, y1, x2, y2 = (int(v) for v in boxes.xyxy[i].tolist())
            conf = float(boxes.conf[i]) if boxes.conf is not None else 0.0
            poses.append(Pose(keypoints=kp_data[i], bbox=(x1, y1, x2, y2), conf=conf))
        return poses

    # ── posture rules (note: image y grows downward) ─────────────────────
    def is_hand_raised(self, pose: Pose) -> bool:
        """True if a wrist is above its shoulder on either side."""
        for side in ("left", "right"):
            sh = pose.kp(f"{side}_shoulder")
            wr = pose.kp(f"{side}_wrist")
            if sh.conf > self.kp_conf and wr.conf > self.kp_conf and wr.y < sh.y:
                return True
        return False

    def _torso_thigh(self, pose: Pose) -> Tuple[Optional[float], Optional[float]]:
        torsos, thighs = [], []
        for side in ("left", "right"):
            sh = pose.kp(f"{side}_shoulder")
            hip = pose.kp(f"{side}_hip")
            kn = pose.kp(f"{side}_knee")
            if sh.conf > self.kp_conf and hip.conf > self.kp_conf:
                torsos.append(hip.y - sh.y)
            if hip.conf > self.kp_conf and kn.conf > self.kp_conf:
                thighs.append(kn.y - hip.y)
        torso = float(np.mean(torsos)) if torsos else None
        thigh = float(np.mean(thighs)) if thighs else None
        return torso, thigh

    def is_sitting(self, pose: Pose) -> bool:
        """Knees near hip level (thigh ~horizontal) => sitting."""
        torso, thigh = self._torso_thigh(pose)
        if torso is None or thigh is None or torso <= 0:
            return False
        return thigh < 0.5 * torso

    def is_standing(self, pose: Pose) -> bool:
        """Knees well below hips (legs extended) => standing."""
        torso, thigh = self._torso_thigh(pose)
        if torso is None or thigh is None or torso <= 0:
            return False
        return thigh >= 0.5 * torso

    # ── association ──────────────────────────────────────────────────────
    @staticmethod
    def iou(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
        return inter / union if union > 0 else 0.0

    def associate(
        self, poses: List[Pose], detections: List[Detection], iou_thr: float = 0.3
    ) -> Dict[int, Pose]:
        """Map ``detection.track_id`` -> best-overlapping Pose (IoU >= iou_thr)."""
        out: Dict[int, Pose] = {}
        for d in detections:
            if d.track_id is None:
                continue
            best, best_iou = None, iou_thr
            for p in poses:
                v = self.iou(d.bbox, p.bbox)
                if v >= best_iou:
                    best, best_iou = p, v
            if best is not None:
                out[d.track_id] = best
        return out
