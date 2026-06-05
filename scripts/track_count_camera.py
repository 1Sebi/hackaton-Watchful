"""Per-camera people counting via tracking (ByteTrack) — the right way to avoid
counting the same person twice within one camera.

Counts UNIQUE track IDs, not raw detections. Reports concurrent vs total-unique:
if total-unique >> max-concurrent, the tracker is fragmenting IDs (the real
'same person counted twice' bug on overhead cams). Saves annotated frames.

  python scripts/track_count_camera.py --ip 192.168.0.59 --password "..." --cam 5 --seconds 30
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;8000000")

import cv2

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--cam", type=int, default=5)
    ap.add_argument("--stream", choices=["main", "sub"], default="sub")
    ap.add_argument("--model", default="yolov8m.pt")
    ap.add_argument("--conf", type=float, default=0.4)
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--imgsz", type=int, default=None)
    args = ap.parse_args()

    from ultralytics import YOLO
    model = YOLO(args.model)

    chan = args.cam * 100 + (1 if args.stream == "main" else 2)
    url = (f"rtsp://admin:{quote(args.password, safe='')}@{args.ip}:554"
           f"/Streaming/Channels/{chan}")
    out_dir = Path("snapshots/track"); out_dir.mkdir(parents=True, exist_ok=True)

    seen_ids: set[int] = set()
    id_frames: dict[int, int] = defaultdict(int)  # how many frames each id lived
    max_concurrent = 0
    frames = 0
    print(f"Tracking {args.ip} cam{args.cam} ({args.stream}) for {args.seconds:.0f}s ...")
    t_end = time.time() + args.seconds
    while time.time() < t_end:
        # stream=True keeps tracker state; persist=True across our manual loop
        kw = dict(classes=[0], conf=args.conf, persist=True, verbose=False,
                  tracker="bytetrack.yaml")
        if args.imgsz:
            kw["imgsz"] = args.imgsz
        # read a frame ourselves so we control the source/timeout
        # (ultralytics can take a URL but we want one cap with our ffmpeg opts)
        if frames == 0:
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            if not cap.isOpened():
                print("FAILED to open stream"); return
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        frames += 1
        res = model.track(frame, **kw)[0]
        ids = []
        if res.boxes is not None and res.boxes.id is not None:
            ids = [int(i) for i in res.boxes.id.cpu().numpy()]
        max_concurrent = max(max_concurrent, len(ids))
        for i in ids:
            seen_ids.add(i)
            id_frames[i] += 1
        if frames % 25 == 0:
            af = res.plot()  # ultralytics draws boxes + ids
            cv2.imwrite(str(out_dir / f"track_{frames}.jpg"), af)
            print(f"  frame {frames}: now={len(ids)}  unique_so_far={len(seen_ids)}",
                  flush=True)
    cap.release()

    # ids that lived only 1-2 frames are likely spurious/flicker
    flicker = sum(1 for c in id_frames.values() if c <= 2)
    print(f"\nDone. {frames} frames.")
    print(f"  max concurrent people : {max_concurrent}")
    print(f"  total UNIQUE track ids : {len(seen_ids)}")
    print(f"  short-lived ids (<=2 frames, likely flicker): {flicker}")
    ratio = len(seen_ids) / max(max_concurrent, 1)
    verdict = ("STABLE — unique ≈ concurrent" if ratio <= 1.6 else
               "FRAGMENTING — same people get new ids (inflates count)")
    print(f"  unique/concurrent ratio: {ratio:.1f}  -> {verdict}")


if __name__ == "__main__":
    main()
