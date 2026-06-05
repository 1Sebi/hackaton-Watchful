"""Pose analyzer test.

  A) Pose on bus.jpg: detect, draw skeletons, save annotated image; standing
     people should report is_standing=True.
  B) Deterministic posture rules on synthetic poses (hand raised / sitting /
     standing / missing-keypoints -> False).
  C) IoU association pose<->detection on bus.jpg.
  D) Pose FPS on webcam.

Usage:  python scripts/test_pose.py
"""
from __future__ import annotations

import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.detector import PersonDetector  # noqa: E402
from backend.core.pose_analyzer import (  # noqa: E402
    COCO_SKELETON,
    KP_INDEX,
    Pose,
    PoseAnalyzer,
)
from backend.core.video_source import VideoSource  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "eval", "screenshots")


def _draw_skeleton(frame, poses, kp_conf=0.3):
    for p in poses:
        kps = p.keypoints
        for a, b in COCO_SKELETON:
            if kps[a][2] > kp_conf and kps[b][2] > kp_conf:
                pa = (int(kps[a][0]), int(kps[a][1]))
                pb = (int(kps[b][0]), int(kps[b][1]))
                cv2.line(frame, pa, pb, (0, 255, 0), 2)
        for x, y, c in kps:
            if c > kp_conf:
                cv2.circle(frame, (int(x), int(y)), 3, (0, 0, 255), -1)
    return frame


def _make_pose(**override) -> Pose:
    """Default = a standing skeleton (conf 0.9); override keypoints by name->(x,y,conf)."""
    base = {
        "nose": (150, 60), "left_eye": (145, 55), "right_eye": (155, 55),
        "left_ear": (140, 60), "right_ear": (160, 60),
        "left_shoulder": (130, 100), "right_shoulder": (170, 100),
        "left_elbow": (120, 150), "right_elbow": (180, 150),
        "left_wrist": (115, 190), "right_wrist": (185, 190),
        "left_hip": (135, 200), "right_hip": (165, 200),
        "left_knee": (133, 300), "right_knee": (167, 300),
        "left_ankle": (132, 390), "right_ankle": (168, 390),
    }
    arr = np.zeros((17, 3), dtype=np.float32)
    for name, (x, y) in base.items():
        i = KP_INDEX[name]
        arr[i] = (x, y, 0.9)
    for name, val in override.items():
        i = KP_INDEX[name]
        arr[i] = val  # (x, y, conf)
    return Pose(keypoints=arr, bbox=(100, 50, 200, 400), conf=0.9)


def part_b_rules(pa: PoseAnalyzer) -> bool:
    standing = _make_pose()
    raised = _make_pose(left_wrist=(115, 80, 0.9))      # wrist above shoulder
    sitting = _make_pose(left_knee=(133, 230, 0.9), right_knee=(167, 230, 0.9))
    missing = _make_pose()
    missing.keypoints[:, 2] = 0.0                        # all keypoints invalid

    checks = {
        "standing.is_standing": pa.is_standing(standing) is True,
        "standing.not_sitting": pa.is_sitting(standing) is False,
        "standing.not_raised": pa.is_hand_raised(standing) is False,
        "raised.is_hand_raised": pa.is_hand_raised(raised) is True,
        "sitting.is_sitting": pa.is_sitting(sitting) is True,
        "sitting.not_standing": pa.is_standing(sitting) is False,
        "missing.no_raise": pa.is_hand_raised(missing) is False,
        "missing.no_sit": pa.is_sitting(missing) is False,
        "missing.no_stand": pa.is_standing(missing) is False,
    }
    for k, v in checks.items():
        print(f"   [B] {k}: {'OK' if v else 'FAIL'}")
    return all(checks.values())


def main() -> int:
    pa = PoseAnalyzer()
    det = PersonDetector()
    print(f"pose_model={pa.model_path}")

    from ultralytics import ASSETS

    img = cv2.imread(str(ASSETS / "bus.jpg"))
    poses = pa.analyze(img)
    standing_n = sum(1 for p in poses if pa.is_standing(p))
    print(f"[A] bus.jpg poses={len(poses)} standing={standing_n}")
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "pose_bus.jpg")
    cv2.imwrite(out, _draw_skeleton(img.copy(), poses))
    print(f"[A] skeleton overlay saved -> {out}")

    rules_ok = part_b_rules(pa)

    dets = det.detect_and_track(cv2.imread(str(ASSETS / "bus.jpg")))
    assoc = pa.associate(poses, dets)
    print(f"[C] associated poses to {len(assoc)}/{len(dets)} tracked detections")

    src = os.environ.get("VIDEO_SOURCE", "0")
    with VideoSource(src) as cam:
        for _ in range(5):
            cam.read()
        frames = [cam.read() for _ in range(30)]
    frames = [f for f in frames if f is not None]
    t = time.time()
    for f in frames:
        pa.analyze(f)
    fps = len(frames) / (time.time() - t)
    print(f"[D] pose FPS on webcam = {fps:.1f}")

    passed = len(poses) >= 1 and standing_n >= 1 and rules_ok and len(assoc) >= 1 and fps >= 10
    print("RESULT:", "PASS" if passed else "FAIL",
          f"(poses:{len(poses)>=1} standing:{standing_n>=1} rules:{rules_ok} assoc:{len(assoc)>=1} fps>=10:{fps>=10})")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
