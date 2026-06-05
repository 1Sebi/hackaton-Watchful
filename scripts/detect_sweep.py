"""Find the most COMPLETE people-detection method on a single frame.

Compares, on one image:
  A) whole-frame @ imgsz 1280
  B) whole-frame @ imgsz 1920
  C) TILED (grid with overlap, detect each tile at full res, merge w/ NMS)

Tiling ("SAHI"-style) zooms into small/distant people that whole-frame inference
downscales away — usually the big win on wide overhead venue shots.

Saves an annotated image per config so we can eyeball who got caught/missed.

  python scripts/detect_sweep.py --img snapshots/192.168.0.59_ch501.jpg
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def iou(a, b):
    ax1, ay1, ax2, ay2 = a; bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    ua = (ax2-ax1)*(ay2-ay1) + (bx2-bx1)*(by2-by1) - inter
    return inter / ua if ua > 0 else 0


def nms(boxes, scores, thr=0.55):
    idx = sorted(range(len(boxes)), key=lambda i: -scores[i])
    keep = []
    while idx:
        i = idx.pop(0); keep.append(i)
        idx = [j for j in idx if iou(boxes[i], boxes[j]) < thr]
    return keep


def detect_whole(model, img, imgsz, conf):
    r = model(img, classes=[0], conf=conf, imgsz=imgsz, verbose=False)[0]
    boxes = r.boxes.xyxy.cpu().numpy().tolist() if r.boxes is not None else []
    scores = r.boxes.conf.cpu().numpy().tolist() if r.boxes is not None else []
    return boxes, scores


def detect_tiled(model, img, conf, cols=3, rows=2, overlap=0.2, imgsz=640):
    H, W = img.shape[:2]
    tw, th = int(W / cols), int(H / rows)
    ox, oy = int(tw * overlap), int(th * overlap)
    allb, alls = [], []
    for r in range(rows):
        for c in range(cols):
            x1 = max(0, c*tw - ox); y1 = max(0, r*th - oy)
            x2 = min(W, (c+1)*tw + ox); y2 = min(H, (r+1)*th + oy)
            tile = img[y1:y2, x1:x2]
            res = model(tile, classes=[0], conf=conf, imgsz=imgsz, verbose=False)[0]
            if res.boxes is None:
                continue
            for b, s in zip(res.boxes.xyxy.cpu().numpy(), res.boxes.conf.cpu().numpy()):
                allb.append([b[0]+x1, b[1]+y1, b[2]+x1, b[3]+y1]); alls.append(float(s))
    keep = nms(allb, alls)
    return [allb[i] for i in keep], [alls[i] for i in keep]


def draw(img, boxes, scores, label):
    im = img.copy()
    for (x1, y1, x2, y2), s in zip(boxes, scores):
        cv2.rectangle(im, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 3)
        cv2.putText(im, f"{s:.2f}", (int(x1), int(y1)-6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    cv2.rectangle(im, (0, 0), (700, 50), (0, 0, 0), -1)
    cv2.putText(im, f"{label}: {len(boxes)} people", (10, 36),
                cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 0), 3)
    return im


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", required=True)
    ap.add_argument("--model", default="yolov8m.pt")
    ap.add_argument("--conf", type=float, default=0.3)
    args = ap.parse_args()

    from ultralytics import YOLO
    model = YOLO(args.model)
    img = cv2.imread(args.img)
    out = Path("snapshots/sweep"); out.mkdir(parents=True, exist_ok=True)

    configs = []
    for name, fn in [
        (f"A_whole_1280", lambda: detect_whole(model, img, 1280, args.conf)),
        (f"B_whole_1920", lambda: detect_whole(model, img, 1920, args.conf)),
        (f"C_tiled_3x2",  lambda: detect_tiled(model, img, args.conf)),
    ]:
        b, s = fn()
        cv2.imwrite(str(out / f"{name}.jpg"), draw(img, b, s, name))
        print(f"  {name:<14} -> {len(b)} people")
        configs.append((name, len(b)))
    best = max(configs, key=lambda x: x[1])
    print(f"\n  most detections: {best[0]} ({best[1]} people) "
          f"-> view snapshots/sweep/{best[0]}.jpg to verify they're real")


if __name__ == "__main__":
    main()
