"""Camera smoke test: open the configured VIDEO_SOURCE, grab frames, and
measure real read throughput (FPS) + resolution.

Usage:
    python scripts/test_camera.py [source]

`source` defaults to the VIDEO_SOURCE env var, then to 0 (webcam).
PASS when we read frames at >= 15 FPS.
"""
from __future__ import annotations

import os
import sys
import time

# allow running as `python scripts/test_camera.py` from the repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.video_source import VideoSource  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


def main() -> int:
    source = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("VIDEO_SOURCE", "0")
    n_frames = 100

    print(f"Opening VIDEO_SOURCE={source!r} ...")
    try:
        with VideoSource(source) as cam:
            print(repr(cam))
            for _ in range(5):  # warmup (first frames are slow)
                cam.read()

            t0 = time.time()
            got = 0
            for _ in range(n_frames):
                frame = cam.read()
                if frame is None:
                    break
                got += 1
            dt = time.time() - t0
            fps = got / dt if dt > 0 else 0.0

            print(f"Read {got}/{n_frames} frames in {dt:.2f}s -> {fps:.1f} FPS")
            print(f"Resolution: {cam.width}x{cam.height}")
            ok = got >= 1 and fps >= 15.0
            print("RESULT:", "PASS" if ok else "FAIL", f"(measured {fps:.1f} FPS, need >= 15)")
            return 0 if ok else 1
    except Exception as e:  # noqa: BLE001
        print(f"ERROR opening source {source!r}: {e}")
        print("Tip: set VIDEO_SOURCE to a file path or RTSP URL in .env")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
