"""Detector + Tracker test.

  A) FPS on live webcam (yolov8n) — must be >= 15.
  B) Person detection on Ultralytics' bundled bus.jpg (local, no network):
     draws bboxes + ids, saves an annotated image for visual inspection.
  C) Track-id persistence across repeated frames.
  D) Deterministic TrackManager test (duration / active_count / prune) with
     injected timestamps.

Usage:  python scripts/test_detector.py
"""
from __future__ import annotations

import os
import sys
import time

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.detector import Detection, PersonDetector  # noqa: E402
from backend.core.tracker import TrackManager  # noqa: E402
from backend.core.video_source import VideoSource  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "eval", "screenshots")


def _draw(frame, dets):
    palette = [(0, 255, 0), (255, 128, 0), (0, 128, 255), (255, 0, 255), (0, 255, 255)]
    for d in dets:
        x1, y1, x2, y2 = d.bbox
        color = palette[(d.track_id or 0) % len(palette)]
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = f"#{d.track_id} {d.conf:.2f}" if d.track_id is not None else f"{d.conf:.2f}"
        cv2.putText(frame, label, (x1, max(0, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return frame


def part_a_fps(det) -> float:
    src = os.environ.get("VIDEO_SOURCE", "0")
    with VideoSource(src) as cam:
        for _ in range(5):
            cam.read()
        frames = [cam.read() for _ in range(40)]
    frames = [f for f in frames if f is not None]
    t = time.time()
    for f in frames:
        det.detect_and_track(f)
    fps = len(frames) / (time.time() - t)
    print(f"[A] webcam FPS (yolov8n) = {fps:.1f}  (need >= 15)")
    return fps


def part_b_bus(det) -> int:
    from ultralytics import ASSETS

    img_path = str(ASSETS / "bus.jpg")
    img = cv2.imread(img_path)
    dets = det.detect(img)  # plain detect (single image)
    print(f"[B] bus.jpg persons detected = {len(dets)} (confs: {[round(d.conf,2) for d in dets]})")
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "detector_bus.jpg")
    cv2.imwrite(out, _draw(img.copy(), dets))
    print(f"[B] annotated saved -> {out}")
    return len(dets)


def part_c_persistence(det) -> bool:
    from ultralytics import ASSETS

    img = cv2.imread(str(ASSETS / "bus.jpg"))
    id_sets = []
    for _ in range(5):
        dets = det.detect_and_track(img)
        id_sets.append({d.track_id for d in dets if d.track_id is not None})
    stable = len(id_sets[-1]) > 0 and id_sets[-1] == id_sets[-2]
    print(f"[C] track ids over 5 frames: {id_sets} -> {'STABLE' if stable else 'unstable'}")
    return stable


def part_d_trackmanager() -> bool:
    tm = TrackManager(prune_after=2.0)
    d1 = Detection(track_id=1, bbox=(10, 10, 50, 90), conf=0.9)
    d2 = Detection(track_id=2, bbox=(60, 10, 100, 90), conf=0.8)
    tm.update([d1, d2], now=100.0)
    tm.update([d1, d2], now=105.0)  # both present 5s later
    ok_dur = abs(tm.duration_of(1) - 5.0) < 1e-6
    ok_active = tm.active_count == 2
    tm.update([d1], now=108.0)  # track 2 vanished; 3s gap > prune_after
    ok_prune = tm.active_count == 1 and 2 not in tm.tracks
    ok_hist = len(tm.tracks[1].positions) == 3
    print(f"[D] duration(1)={tm.duration_of(1):.1f}s active={tm.active_count} "
          f"dur_ok={ok_dur} active_ok={ok_active} prune_ok={ok_prune} hist_ok={ok_hist}")
    return ok_dur and ok_active and ok_prune and ok_hist


def main() -> int:
    det = PersonDetector()
    print(f"model={det.model_path} conf={det.conf}")
    fps = part_a_fps(det)
    n_bus = part_b_bus(det)
    stable = part_c_persistence(det)
    tm_ok = part_d_trackmanager()

    passed = fps >= 15 and n_bus >= 1 and stable and tm_ok
    print("RESULT:", "PASS" if passed else "FAIL",
          f"(fps>=15:{fps>=15} bus_persons:{n_bus>=1} id_stable:{stable} trackmgr:{tm_ok})")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
