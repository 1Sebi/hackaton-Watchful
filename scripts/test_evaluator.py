"""HybridEvaluator test — each evaluator type produces the correct result, plus
adaptive VLM sampling (1 FPS) reuses cached results.

  YOLO : count gt/lt, presence-in-zone, absence-for-duration
  POSE : standing (real), hand-raised (real False + synthetic True)
  VLM  : semantic question on bus.jpg ("is there a bus?")
  SAMPLING: repeated VLM calls within the interval don't re-invoke the model

Usage:  python scripts/test_evaluator.py
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.detector import PersonDetector  # noqa: E402
from backend.core.pose_analyzer import KP_INDEX, Pose, PoseAnalyzer  # noqa: E402
from backend.predicates.evaluator import EvalContext, HybridEvaluator  # noqa: E402
from backend.predicates.types import Predicate, PredicateType  # noqa: E402
from backend.vlm.client import OllamaVLMClient  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


def _raised_pose() -> Pose:
    base = {
        "left_shoulder": (130, 100), "right_shoulder": (170, 100),
        "left_wrist": (120, 60), "right_wrist": (185, 190),   # left wrist above shoulder
        "left_hip": (135, 200), "right_hip": (165, 200),
        "left_knee": (133, 300), "right_knee": (167, 300),
    }
    arr = np.zeros((17, 3), dtype=np.float32)
    for name, (x, y) in base.items():
        arr[KP_INDEX[name]] = (x, y, 0.9)
    return Pose(keypoints=arr, bbox=(100, 50, 200, 350), conf=0.9)


def main() -> int:
    det = PersonDetector()
    pose = PoseAnalyzer()
    vlm = OllamaVLMClient()
    ev = HybridEvaluator(pose_analyzer=pose, vlm=vlm, vlm_max_fps=1.0)

    from ultralytics import ASSETS

    img = cv2.imread(str(ASSETS / "bus.jpg"))
    dets = det.detect_and_track(img)
    poses = pose.analyze(img)
    pmap = pose.associate(poses, dets)
    n = len(dets)
    print(f"bus.jpg: detections={n} poses={len(poses)}")

    d0 = dets[0]
    x1, y1, x2, y2 = d0.bbox
    zones = {
        "area": [(x1 - 5, y1 - 5), (x2 + 5, y1 - 5), (x2 + 5, y2 + 5), (x1 - 5, y2 + 5)],
        "empty": [(0, 0), (4, 0), (4, 4), (0, 4)],
    }
    ctx = EvalContext(frame=img, detections=dets, poses=poses, pose_map=pmap, zones=zones, now=1000.0)

    def P(**kw):
        return Predicate(**kw)

    checks = {}
    checks["count_gt_2"] = ev.evaluate(P(type=PredicateType.COUNT_GT, params={"value": 2}), ctx).detected is True
    checks["count_gt_5"] = ev.evaluate(P(type=PredicateType.COUNT_GT, params={"value": 5}), ctx).detected is False
    checks["count_lt_5"] = ev.evaluate(P(type=PredicateType.COUNT_LT, params={"value": 5}), ctx).detected is True
    checks["zone_area"] = ev.evaluate(P(type=PredicateType.PRESENCE_IN_ZONE, params={"zone": "area"}), ctx).detected is True
    checks["zone_empty"] = ev.evaluate(P(type=PredicateType.PRESENCE_IN_ZONE, params={"zone": "empty"}), ctx).detected is False
    checks["pose_standing"] = ev.evaluate(P(type=PredicateType.POSE_STANDING), ctx).detected is True
    checks["pose_raised_real_false"] = ev.evaluate(P(type=PredicateType.POSE_HAND_RAISED), ctx).detected is False

    ctx_raised = EvalContext(poses=[_raised_pose()], now=1000.0)
    checks["pose_raised_synth_true"] = ev.evaluate(P(type=PredicateType.POSE_HAND_RAISED), ctx_raised).detected is True

    # absence-for-duration over simulated time
    abs_p = P(type=PredicateType.ABSENCE_FOR_DURATION, params={"seconds": 5}, original_text="empty 5s")
    empty100 = EvalContext(detections=[], now=100.0)
    empty106 = EvalContext(detections=[], now=106.0)
    present110 = EvalContext(detections=dets, now=110.0)
    r0 = ev.evaluate(abs_p, empty100).detected   # init -> False
    r1 = ev.evaluate(abs_p, empty106).detected   # 6s >= 5 -> True
    r2 = ev.evaluate(abs_p, present110).detected  # present -> False
    checks["absence"] = (r0 is False and r1 is True and r2 is False)

    # VLM semantic on bus.jpg
    bus_q = P(type=PredicateType.SEMANTIC,
              visual_question='Is there a bus in this image? Answer JSON {"detected": bool, "confidence": 0-1, "reason": str}')
    sem = ev.evaluate(bus_q, ctx)
    checks["vlm_bus_true"] = sem.detected is True
    print(f"   [vlm] bus? detected={sem.detected} conf={sem.confidence} reason={sem.reason!r}")

    # adaptive sampling: within 1s interval -> cached (no new model call)
    before = ev.vlm_calls
    ctx.now = 1000.0
    ev.evaluate(bus_q, ctx)        # cached (same now)
    ctx.now = 1000.4
    ev.evaluate(bus_q, ctx)        # cached (<1s)
    cached_ok = (ev.vlm_calls == before)
    ctx.now = 1002.0
    ev.evaluate(bus_q, ctx)        # >1s -> new call
    fresh_ok = (ev.vlm_calls == before + 1)
    checks["adaptive_sampling"] = cached_ok and fresh_ok

    passed = 0
    for k, v in checks.items():
        print(f"   [{'OK' if v else 'XX'}] {k}")
        passed += bool(v)
    print(f"RESULT: {passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
