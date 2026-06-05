"""Record N seconds of the annotated live feed to an mp4 — the demo safety net.

Usage:  python scripts/record_demo.py [seconds] [out.mp4]
Default: 60s -> eval/clips/demo_backup.mp4 (gitignored).
"""
from __future__ import annotations

import os
import sys
import time

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.detector import PersonDetector  # noqa: E402
from backend.core.pose_analyzer import PoseAnalyzer  # noqa: E402
from backend.core.tracker import TrackManager  # noqa: E402
from backend.core.video_source import VideoSource  # noqa: E402
from backend.visualizer import draw_overlay  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


def main() -> int:
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join("eval", "clips", "demo_backup.mp4")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    det = PersonDetector()
    pose = PoseAnalyzer()
    tracker = TrackManager()
    cam = VideoSource(os.environ.get("VIDEO_SOURCE", "0"))
    w, h = cam.width or 640, cam.height or 480
    vw = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*"mp4v"), 20, (w, h))

    t0 = time.time()
    n = 0
    while time.time() - t0 < secs:
        frame = cam.read()
        if frame is None:
            break
        dets = det.detect_and_track(frame)
        poses = pose.analyze(frame)
        pmap = pose.associate(poses, dets)
        tracker.update(dets)
        state = {"fps": round(n / max(1e-6, time.time() - t0), 1),
                 "persons": tracker.active_count, "conditions": 0}
        ann = draw_overlay(frame, dets, pmap, tracker, state, {})
        if ann.shape[1] != w or ann.shape[0] != h:
            ann = cv2.resize(ann, (w, h))
        vw.write(ann)
        n += 1

    vw.release()
    cam.release()
    size = os.path.getsize(out) if os.path.exists(out) else 0
    print(f"recorded {n} frames -> {out} ({size} bytes)")
    return 0 if n > 0 and size > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
