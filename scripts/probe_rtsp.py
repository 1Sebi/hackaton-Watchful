"""Probe a Hikvision NVR RTSP stream and grab one frame.

Credentials are passed as args (never hard-coded / committed). Passwords with
@ : / $ etc. are URL-encoded automatically.

  python scripts/probe_rtsp.py --ip 192.168.0.59 --user admin --password "2020@Doina"
  python scripts/probe_rtsp.py --ip 192.168.0.60 --user admin --password "@WallySpeed2105$" --channel 1 --stream sub

Hikvision channel id = camera*100 + stream  (stream: 1=main, 2=sub).
Saves the captured frame to snapshots/<ip>_ch<n>.jpg (gitignored).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

# Give FFMPEG a short, TCP-based timeout so a dead stream fails fast instead of
# hanging forever.
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|stimeout;8000000",
)

import cv2

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def build_url(ip, user, password, camera, stream, port=554):
    u = quote(user, safe="")
    p = quote(password, safe="")
    chan = camera * 100 + (1 if stream == "main" else 2)
    return f"rtsp://{u}:{p}@{ip}:{port}/Streaming/Channels/{chan}", chan


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", required=True)
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", required=True)
    ap.add_argument("--camera", type=int, default=1, help="camera/channel number")
    ap.add_argument("--stream", choices=["main", "sub"], default="sub")
    ap.add_argument("--port", type=int, default=554)
    args = ap.parse_args()

    url, chan = build_url(args.ip, args.user, args.password,
                          args.camera, args.stream, args.port)
    # masked URL for logging (don't print the password)
    masked = url.replace(quote(args.password, safe=""), "***")
    print(f"Connecting: {masked}")

    t0 = time.time()
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print(f"  FAILED to open stream (after {time.time()-t0:.1f}s).")
        print("  -> check: credentials, channel number, port 554, firewall.")
        sys.exit(2)

    # Warm up: the first frames of an H.264 stream are often partial/gray until
    # the decoder hits a keyframe. Read several and keep the last good one.
    frame = None
    for _ in range(30):
        ok, f = cap.read()
        if ok and f is not None:
            frame = f
    if frame is None:
        print("  Stream opened but no frame received.")
        cap.release()
        sys.exit(3)

    h, w = frame.shape[:2]
    out_dir = Path("snapshots")
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{args.ip}_ch{chan}.jpg"
    cv2.imwrite(str(out), frame)
    print(f"  SUCCESS ✅  frame {w}x{h}  in {time.time()-t0:.1f}s")
    print(f"  saved -> {out.resolve()}")
    cap.release()


if __name__ == "__main__":
    main()
