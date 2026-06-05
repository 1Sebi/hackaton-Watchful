"""Visualizer test — render all overlays (zones, trails, skeletons, labeled
bboxes, HUD) onto bus.jpg and save for visual inspection. Also confirms the
pipeline auto-imported the pro visualizer.

Usage:  python scripts/test_visualizer.py
"""
from __future__ import annotations

import collections
import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.detector import PersonDetector  # noqa: E402
from backend.core.pose_analyzer import PoseAnalyzer  # noqa: E402
from backend.core.tracker import TrackManager  # noqa: E402
from backend.visualizer import draw_overlay  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "eval", "screenshots")


def main() -> int:
    from ultralytics import ASSETS

    img = cv2.imread(str(ASSETS / "bus.jpg"))
    det = PersonDetector()
    pose = PoseAnalyzer()
    dets = det.detect_and_track(img)
    poses = pose.analyze(img)
    pmap = pose.associate(poses, dets)

    tracker = TrackManager()
    tracker.update(dets, now=1000.0)
    # synthesize trails + non-zero durations for a representative render
    for i, (tid, t) in enumerate(tracker.tracks.items()):
        t.first_seen = 1000.0 - (i + 1) * 4  # 4s, 8s, ...
        c = t.positions[-1]
        trail = [(c[0] - k * 9, c[1] + k * 5) for k in range(8, 0, -1)] + [c]
        t.positions = collections.deque(trail, maxlen=64)

    h, w = img.shape[:2]
    zones = {"pool": [[int(w * 0.18), int(h * 0.45)], [int(w * 0.6), int(h * 0.45)],
                      [int(w * 0.6), int(h * 0.9)], [int(w * 0.18), int(h * 0.9)]]}
    state = {"fps": 24, "persons": len(dets), "conditions": 2,
             "last_event": {"text": "more than 2 people in the pool"}}

    out = draw_overlay(img, dets, pmap, tracker, state, zones)
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "visualizer.jpg")
    cv2.imwrite(path, out)

    # pipeline should have auto-imported the pro visualizer
    import backend.core.pipeline as P

    checks = {
        "render_ok": out is not None and out.shape == img.shape,
        "has_people": len(dets) >= 1,
        "pipeline_uses_visualizer": P._draw_overlay is not None,
    }
    print(f"saved -> {path}  (dets={len(dets)})")
    passed = 0
    for k, v in checks.items():
        print(f"   [{'OK' if v else 'XX'}] {k}")
        passed += bool(v)
    print(f"RESULT: {passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
