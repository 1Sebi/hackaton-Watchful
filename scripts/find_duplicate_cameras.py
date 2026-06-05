"""Find DUPLICATE camera feeds across both NVRs — the same physical camera
registered on .59 and .60 would otherwise make us count people twice.

Captures one frame from every camera on both NVRs, then cross-correlates all
pairs. High correlation => same physical camera. Prints duplicate groups and
the resulting set of UNIQUE cameras.

  python scripts/find_duplicate_cameras.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import quote

os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;6000000")

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


# cameras to fingerprint per NVR
CAMS = {
    "NVR1": [1, 2, 3, 4, 5, 6, 7, 8],
    "NVR2": [1, 2, 3, 4, 5, 6, 7, 9, 10, 12, 13, 15, 16],
}


def grab_gray(ip, pw, cam):
    chan = cam * 100 + 2  # sub-stream
    url = f"rtsp://admin:{quote(pw, safe='')}@{ip}:554/Streaming/Channels/{chan}"
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        cap.release(); return None
    frame = None
    for _ in range(8):
        ok, f = cap.read()
        if ok and f is not None:
            frame = f
    cap.release()
    if frame is None:
        return None
    g = cv2.cvtColor(cv2.resize(frame, (320, 180)), cv2.COLOR_BGR2GRAY)
    return g.astype(float)


def corr(a, b):
    return float(np.corrcoef(a.ravel(), b.ravel())[0, 1])


def main() -> None:
    env = load_env()
    ips = {"NVR1": env["NVR1_IP"], "NVR2": env["NVR2_IP"]}
    pws = {"NVR1": env["NVR1_PASS"], "NVR2": env["NVR2_PASS"]}

    prints = {}  # (nvr,cam) -> gray
    for nvr, cams in CAMS.items():
        for cam in cams:
            g = grab_gray(ips[nvr], pws[nvr], cam)
            if g is not None:
                prints[(nvr, cam)] = g
                print(f"  fingerprinted {nvr} cam{cam}", flush=True)

    keys = list(prints)
    dups = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            c = corr(prints[keys[i]], prints[keys[j]])
            if c > 0.90:
                dups.append((keys[i], keys[j], c))

    print("\n=== DUPLICATE feeds (same physical camera, corr>0.90) ===")
    if not dups:
        print("  none — all cameras are distinct")
    for a, b, c in sorted(dups, key=lambda x: -x[2]):
        print(f"  {a[0]} cam{a[1]}  ==  {b[0]} cam{b[1]}   (corr {c:.3f})")

    # unique set: drop the second of each duplicate pair
    drop = set()
    for a, b, c in dups:
        if a not in drop:
            drop.add(b)
    unique = [k for k in keys if k not in drop]
    print(f"\n=== {len(keys)} feeds total -> {len(unique)} UNIQUE physical cameras ===")
    print("  unique:", ", ".join(f"{n}c{c}" for n, c in unique))
    print("  duplicates dropped:", ", ".join(f"{n}c{c}" for n, c in drop) or "none")


if __name__ == "__main__":
    main()
