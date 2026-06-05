"""Plain live RTSP viewer (no AI) — confirm the stream flows smoothly.

  python scripts/live_view.py --ip 192.168.0.59 --password "2020@Doina" --cam 5
  python scripts/live_view.py --ip 192.168.0.60 --password "@WallySpeed2105$" --cam 3 --stream main

Keys in the window:  q / Esc = quit   ·   s = save a snapshot
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
    ap.add_argument("--cam", type=int, default=1)
    ap.add_argument("--stream", choices=["main", "sub"], default="sub")
    args = ap.parse_args()

    chan = args.cam * 100 + (1 if args.stream == "main" else 2)
    url = (f"rtsp://{quote(args.user, safe='')}:{quote(args.password, safe='')}"
           f"@{args.ip}:554/Streaming/Channels/{chan}")
    print(f"Opening cam {args.cam} ({args.stream}) on {args.ip} ... q=quit  s=snapshot")

    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print("  FAILED to open stream.")
        return

    win = f"Watchful LIVE - {args.ip} cam{args.cam} ({args.stream}) - q=quit"
    fps, t_prev, frames, drops = 0.0, time.time(), 0, 0
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            drops += 1
            if drops > 100:
                print("  too many dropped frames, stream stalled.")
                break
            continue
        frames += 1
        now = time.time()
        fps = 0.9 * fps + 0.1 * (1.0 / max(now - t_prev, 1e-6))
        t_prev = now
        cv2.putText(frame, f"cam{args.cam} {args.stream}  FPS:{fps:4.1f}  frames:{frames}",
                    (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow(win, frame)
        k = cv2.waitKey(1) & 0xFF
        if k in (ord("q"), 27):
            break
        if k == ord("s"):
            Path("snapshots").mkdir(exist_ok=True)
            p = Path("snapshots") / f"live_{args.ip}_cam{args.cam}_{frames}.jpg"
            cv2.imwrite(str(p), frame)
            print(f"  saved {p}")

    cap.release()
    cv2.destroyAllWindows()
    print(f"Done. {frames} frames shown, {drops} drops.")


if __name__ == "__main__":
    main()
