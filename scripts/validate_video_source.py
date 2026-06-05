"""Validate the project's VideoSource (backend/core/video_source.py) against a
REAL Hikvision RTSP camera — the test the cloud agent can't run (no NVR access).

Run twice: once WITHOUT the FFmpeg TCP/timeout option (the current main code
path), once WITH it, to show the difference on a real cross-subnet stream.

  python scripts/validate_video_source.py --ip 192.168.0.59 --password "<NVR1_PASS>" --cam 5
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from urllib.parse import quote

# Toggle BEFORE importing cv2/VideoSource (FFmpeg reads it at import/open time).
if os.environ.get("USE_TCP") == "1":
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;8000000"

from backend.core.video_source import VideoSource  # noqa: E402

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
    ap.add_argument("--frames", type=int, default=120)
    args = ap.parse_args()

    chan = args.cam * 100 + (1 if args.stream == "main" else 2)
    url = (f"rtsp://{quote(args.user, safe='')}:{quote(args.password, safe='')}"
           f"@{args.ip}:554/Streaming/Channels/{chan}")
    tcp = os.environ.get("USE_TCP") == "1"
    print(f"VideoSource test  cam{args.cam}/{args.stream}  TCP_option={tcp}")

    t0 = time.time()
    try:
        vs = VideoSource(url)
    except Exception as e:
        print(f"  OPEN FAILED: {e}")
        sys.exit(2)
    print(f"  opened in {time.time()-t0:.1f}s -> {vs!r}")

    got, none_count, gray = 0, 0, 0
    t = time.time()
    for i in range(args.frames):
        f = vs.read()
        if f is None:
            none_count += 1
            continue
        got += 1
        # crude "gray/partial frame" check: very low pixel variance
        if i < 5 and float(f.std()) < 8.0:
            gray += 1
    dt = time.time() - t
    vs.release()
    fps = got / dt if dt > 0 else 0
    print(f"  frames ok={got}  none={none_count}  early_gray={gray}")
    print(f"  effective FPS={fps:4.1f} over {dt:.1f}s")
    print("  RESULT:", "✅ usable" if got > args.frames * 0.8 else "⚠️ unreliable")


if __name__ == "__main__":
    main()
