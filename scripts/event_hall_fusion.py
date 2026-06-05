"""Apply homography fusion to event_hall (NVR2/ch1 + NVR2/ch5).

Calibration without a floor plan: ONE person stands at 4 distinct spots in the
overlap region; at each spot we auto-detect their feet in BOTH cameras -> that's
one correspondence. The 4 spots define a shared floor frame (a unit quad), so
both cameras map to the same plane and fusion can dedup people.

  # 1) calibrate — person stands still at spot i, run for each i in 0..3:
  python scripts/event_hall_fusion.py calib --spot 0
  python scripts/event_hall_fusion.py calib --spot 1   # person moves, repeat
  python scripts/event_hall_fusion.py calib --spot 2
  python scripts/event_hall_fusion.py calib --spot 3
  # 2) build the homographies from the 4 captured spots:
  python scripts/event_hall_fusion.py build
  # 3) live deduped count across both cameras:
  python scripts/event_hall_fusion.py run --seconds 30
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;8000000")

import cv2
import numpy as np

sys.path.insert(0, ".")
from backend.core.homography_fusion import CameraFloorMap, RoomCounter  # noqa

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CALIB = Path("config/event_hall_calib.json")
# the two cameras of the room (from config/cameras.yaml)
CAMS = {"confSE": ("NVR2", 1), "hallN": ("NVR2", 5)}
# the 4 calibration spots, as arbitrary-but-shared floor coords (a unit square)
SPOT_FLOOR = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]


def env(path=".env"):
    d = {}
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        if "=" in ln and not ln.strip().startswith("#"):
            k, v = ln.split("=", 1); d[k.strip()] = v.strip()
    return d


def grab(ip, pw, cam, warmup=8):
    url = f"rtsp://admin:{quote(pw, safe='')}@{ip}:554/Streaming/Channels/{cam*100+2}"
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    f = None
    for _ in range(warmup):
        ok, fr = cap.read()
        if ok and fr is not None:
            f = fr
    cap.release()
    return f


def feet_of_main_person(model, frame):
    """Return feet (x, bottom) of the most confident person, or None."""
    r = model(frame, classes=[0], conf=0.3, imgsz=1280, verbose=False)[0]
    if r.boxes is None or len(r.boxes) == 0:
        return None
    confs = r.boxes.conf.cpu().numpy()
    i = int(confs.argmax())
    x1, y1, x2, y2 = r.boxes.xyxy.cpu().numpy()[i]
    return [float((x1 + x2) / 2), float(y2)]


def all_boxes(model, frame):
    r = model(frame, classes=[0], conf=0.3, imgsz=1280, verbose=False)[0]
    return r.boxes.xyxy.cpu().numpy().tolist() if r.boxes is not None else []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["calib", "build", "run"])
    ap.add_argument("--spot", type=int)
    ap.add_argument("--seconds", type=float, default=30)
    args = ap.parse_args()

    e = env()
    ip = {"NVR1": e["NVR1_IP"], "NVR2": e["NVR2_IP"]}
    pw = {"NVR1": e["NVR1_PASS"], "NVR2": e["NVR2_PASS"]}
    from ultralytics import YOLO
    model = YOLO("yolov8m.pt")

    if args.mode == "calib":
        data = json.loads(CALIB.read_text()) if CALIB.exists() else {}
        for label, (nvr, cam) in CAMS.items():
            fr = grab(ip[nvr], pw[nvr], cam)
            ft = feet_of_main_person(model, fr) if fr is not None else None
            if ft is None:
                print(f"  {label}: NO person detected — reposition and retry"); return
            data.setdefault(label, {})[str(args.spot)] = ft
            print(f"  spot {args.spot} {label}: feet={ft}")
        CALIB.parent.mkdir(exist_ok=True)
        CALIB.write_text(json.dumps(data, indent=2))
        print(f"  saved spot {args.spot}. Capture all 4 spots, then 'build'.")

    elif args.mode == "build":
        data = json.loads(CALIB.read_text())
        maps = {}
        for label in CAMS:
            img_pts = [data[label][str(i)] for i in range(4)]
            maps[label] = CameraFloorMap.from_points(label, img_pts, SPOT_FLOOR)
            err = maps[label].reproj_error(img_pts, SPOT_FLOOR)
            print(f"  {label}: homography built, reproj err {err:.3f}")
        data["_built"] = True
        CALIB.write_text(json.dumps(data, indent=2))
        print("  calibration ready -> run")

    elif args.mode == "run":
        import time
        data = json.loads(CALIB.read_text())
        cams = [CameraFloorMap.from_points(l, [data[l][str(i)] for i in range(4)],
                                           SPOT_FLOOR) for l in CAMS]
        rc = RoomCounter(cams, merge_dist=0.25)  # 0.25 of the unit-square side
        t_end = time.time() + args.seconds
        while time.time() < t_end:
            boxes = {}
            for label, (nvr, cam) in CAMS.items():
                fr = grab(ip[nvr], pw[nvr], cam, warmup=2)
                boxes[label] = all_boxes(model, fr) if fr is not None else []
            res = rc.fuse(boxes)
            print(f"  naive_sum={res['naive_sum']}  DEDUP_COUNT={res['count']}  "
                  f"(removed {res['merged_from']} duplicates)", flush=True)


if __name__ == "__main__":
    main()
