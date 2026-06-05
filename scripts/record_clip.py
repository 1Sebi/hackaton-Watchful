"""Record a real clip from an NVR camera into the eval set.

Clips are the non-duplicable core of PAS 14 — only a machine on the venue LAN
can make them. Saved (gitignored) under eval/clips/<label>/<name>.mp4.

  python scripts/record_clip.py --ip 192.168.0.59 --password "2020@Doina" --cam 5 \
      --label neutral --name restaurant_empty_01 --seconds 8

Labels by convention: true | trap | neutral
"""
from __future__ import annotations

import argparse
import os
import sys
import time
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
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", required=True)
    ap.add_argument("--cam", type=int, default=5)
    ap.add_argument("--stream", choices=["main", "sub"], default="sub")
    ap.add_argument("--label", default="neutral", help="true | trap | neutral")
    ap.add_argument("--name", required=True, help="clip base name (no extension)")
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--fps", type=float, default=15.0, help="output file FPS")
    args = ap.parse_args()

    chan = args.cam * 100 + (1 if args.stream == "main" else 2)
    url = (f"rtsp://{quote(args.user, safe='')}:{quote(args.password, safe='')}"
           f"@{args.ip}:554/Streaming/Channels/{chan}")

    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print("  FAILED to open stream.")
        sys.exit(2)

    # warm up past the gray keyframe-less frames
    frame = None
    for _ in range(10):
        ok, f = cap.read()
        if ok and f is not None:
            frame = f
    if frame is None:
        print("  no frame after warmup.")
        sys.exit(3)
    h, w = frame.shape[:2]

    out_dir = Path("eval/clips") / args.label
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{args.name}.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out), fourcc, args.fps, (w, h))

    print(f"Recording {args.seconds:.0f}s  cam{args.cam}/{args.stream} {w}x{h} "
          f"-> {out}  (label={args.label})")
    t_end = time.time() + args.seconds
    n = 0
    while time.time() < t_end:
        ok, f = cap.read()
        if not ok or f is None:
            continue
        writer.write(f)
        n += 1
    writer.release()
    cap.release()
    size_kb = out.stat().st_size // 1024
    print(f"  done: {n} frames, {size_kb} KB -> {out.resolve()}")


if __name__ == "__main__":
    main()
