"""Grab a sub-stream thumbnail from each camera on an NVR and tile them into a
single contact-sheet image, so we can eyeball all the angles at once.

  python scripts/contact_sheet.py --ip 192.168.0.60 --password "<NVR2_PASS>" --cams 1-16
  python scripts/contact_sheet.py --ip 192.168.0.59 --password "<NVR1_PASS>" --cams 1-8
"""
from __future__ import annotations

import argparse
import math
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


def parse_cams(s: str) -> list[int]:
    out: list[int] = []
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def grab(ip, user, pw, cam, warmup=12):
    chan = cam * 100 + 2  # sub-stream
    url = f"rtsp://{quote(user, safe='')}:{quote(pw, safe='')}@{ip}:554/Streaming/Channels/{chan}"
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        cap.release()
        return None
    frame = None
    for _ in range(warmup):
        ok, f = cap.read()
        if ok and f is not None:
            frame = f
    cap.release()
    return frame


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", required=True)
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", required=True)
    ap.add_argument("--cams", default="1-16")
    ap.add_argument("--tw", type=int, default=320, help="thumbnail width")
    args = ap.parse_args()

    cams = parse_cams(args.cams)
    thumbs = []
    for cam in cams:
        print(f"  cam {cam} ...", end=" ", flush=True)
        f = grab(args.ip, args.user, args.password, cam)
        if f is None:
            print("no stream")
            continue
        th = int(args.tw * f.shape[0] / f.shape[1])
        f = cv2.resize(f, (args.tw, th))
        cv2.rectangle(f, (0, 0), (90, 24), (0, 0, 0), -1)
        cv2.putText(f, f"cam {cam}", (5, 17), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (0, 255, 0), 2)
        thumbs.append(f)
        print("ok")

    if not thumbs:
        print("No streams captured.")
        return

    cols = min(4, len(thumbs))
    rows = math.ceil(len(thumbs) / cols)
    th, tw = thumbs[0].shape[:2]
    sheet = np.zeros((rows * th, cols * tw, 3), dtype=np.uint8)
    for i, t in enumerate(thumbs):
        r, c = divmod(i, cols)
        sheet[r*th:(r+1)*th, c*tw:(c+1)*tw] = t

    out = Path("snapshots") / f"contact_{args.ip}.jpg"
    out.parent.mkdir(exist_ok=True)
    cv2.imwrite(str(out), sheet)
    print(f"\nSaved contact sheet ({len(thumbs)} cams) -> {out.resolve()}")


if __name__ == "__main__":
    main()
