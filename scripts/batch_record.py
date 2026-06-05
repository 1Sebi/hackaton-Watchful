"""Record a batch of real ambient clips for the PAS 14 eval set, then build a
preview montage (one mid-frame per clip) so we can label ground truth by eye.

Reads NVR passwords from .env (NVR1_PASS / NVR2_PASS) — never hard-coded.
Clips -> eval/clips/ambient/<name>.mp4 (gitignored). Montage -> eval/preview.jpg.

  python scripts/batch_record.py --seconds 6
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;8000000")

import cv2
import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def load_env(path=".env") -> dict:
    env = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


# (nvr_key, ip_key, pass_key, cam, scene-name, guess)
# guess is only a hint for ordering; real label is set after viewing.
CLIPS = [
    ("NVR1", 5, "restaurant_a", "people?"),
    ("NVR1", 5, "restaurant_b", "people?"),
    ("NVR1", 2, "lobby", "people?"),
    ("NVR1", 7, "lobby_bar", "people?"),
    ("NVR1", 1, "w_entrance", "empty?"),
    ("NVR1", 3, "east_exit_glass", "trap-reflection"),
    ("NVR1", 6, "north_parking", "trap-cars"),
    ("NVR2", 7, "reception", "people?"),
    ("NVR2", 6, "restaurant_bar", "people?"),
    ("NVR2", 9, "lobby_bar2", "people?"),
    ("NVR2", 1, "conference", "empty?"),
    ("NVR2", 16, "wine_cellar", "empty?"),
    ("NVR2", 15, "gym", "empty?"),
    ("NVR2", 12, "west_parking", "trap-cars"),
]


def rtsp(ip, pw, cam, stream="sub"):
    chan = cam * 100 + (1 if stream == "main" else 2)
    return (f"rtsp://admin:{quote(pw, safe='')}@{ip}:554/Streaming/Channels/{chan}")


def record(url, out: Path, seconds: float, fps: float = 15.0):
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        return None
    frame = None
    for _ in range(10):
        ok, f = cap.read()
        if ok and f is not None:
            frame = f
    if frame is None:
        cap.release()
        return None
    h, w = frame.shape[:2]
    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    mid = None
    t_end = time.time() + seconds
    n = 0
    while time.time() < t_end:
        ok, f = cap.read()
        if not ok or f is None:
            continue
        writer.write(f)
        n += 1
        if mid is None and time.time() > t_end - seconds / 2:
            mid = f.copy()
    writer.release()
    cap.release()
    return (n, mid if mid is not None else frame, (w, h))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=6.0)
    args = ap.parse_args()

    env = load_env()
    ips = {"NVR1": env.get("NVR1_IP"), "NVR2": env.get("NVR2_IP")}
    pws = {"NVR1": env.get("NVR1_PASS"), "NVR2": env.get("NVR2_PASS")}

    out_dir = Path("eval/clips/ambient")
    out_dir.mkdir(parents=True, exist_ok=True)
    thumbs = []
    for nvr, cam, name, guess in CLIPS:
        out = out_dir / f"{name}.mp4"
        url = rtsp(ips[nvr], pws[nvr], cam)
        print(f"  {nvr} cam{cam:<2} {name:<18} ...", end=" ", flush=True)
        res = record(url, out, args.seconds)
        if res is None:
            print("no stream")
            continue
        n, mid, (w, h) = res
        print(f"{n} frames")
        th = cv2.resize(mid, (320, int(320 * h / w)))
        cv2.rectangle(th, (0, 0), (320, 22), (0, 0, 0), -1)
        cv2.putText(th, f"{name}", (4, 16), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (0, 255, 0), 1)
        thumbs.append(th)

    if thumbs:
        cols = 4
        rows = math.ceil(len(thumbs) / cols)
        th, tw = thumbs[0].shape[:2]
        sheet = np.zeros((rows * th, cols * tw, 3), dtype=np.uint8)
        for i, t in enumerate(thumbs):
            r, c = divmod(i, cols)
            sheet[r*th:(r+1)*th, c*tw:(c+1)*tw] = t
        prev = Path("eval/preview.jpg")
        cv2.imwrite(str(prev), sheet)
        print(f"\nRecorded {len(thumbs)} clips. Preview -> {prev.resolve()}")


if __name__ == "__main__":
    main()
