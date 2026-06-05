"""Probe the configured VIDEO_SOURCE (or a CLI arg): TCP reachability + RTSP
frame grab + measured FPS + a saved snapshot. Passwords are masked in output.

Usage:  python scripts/probe_camera.py [rtsp_url_or_index]
"""
from __future__ import annotations

import os
import re
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from backend.core.video_source import VideoSource  # noqa: E402
import cv2  # noqa: E402


def _mask(s: str) -> str:
    return re.sub(r"://([^:@/]+):[^@/]+@", r"://\1:***@", str(s))


def main() -> int:
    src = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("VIDEO_SOURCE", "0")
    m = re.search(r"@([\d.]+):(\d+)", str(src))
    if m:
        host, port = m.group(1), int(m.group(2))
        s = socket.socket()
        s.settimeout(4)
        try:
            s.connect((host, port))
            print(f"TCP {host}:{port} OPEN")
        except Exception as e:  # noqa: BLE001
            print(f"TCP {host}:{port} FAIL: {e}")
            print("PROBE_FAIL: not on the camera LAN? check Wi-Fi / IP")
            return 2
        finally:
            s.close()

    print("opening:", _mask(src))
    try:
        with VideoSource(src) as cam:
            print(repr(cam))
            for _ in range(5):
                cam.read()
            t = time.time()
            n = 0
            last = None
            for _ in range(60):
                f = cam.read()
                if f is None:
                    break
                last = f
                n += 1
            dt = time.time() - t
            fps = n / dt if dt > 0 else 0.0
            print(f"read {n}/60 frames -> {fps:.1f} FPS, res {cam.width}x{cam.height}")
            if last is not None:
                os.makedirs(os.path.join("eval", "screenshots"), exist_ok=True)
                out = os.path.join("eval", "screenshots", "real_cam.jpg")
                cv2.imwrite(out, last)
                print(f"snapshot -> {out}")
                print("PROBE_OK" if n >= 10 else "PROBE_FEW_FRAMES")
                return 0 if n >= 10 else 1
            print("PROBE_NO_FRAMES")
            return 1
    except Exception as e:  # noqa: BLE001
        print("PROBE_FAIL:", e)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
