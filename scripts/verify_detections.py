"""Draw YOLO person boxes on sampled frames of a clip and save them, so we can
visually verify whether a 'person' detection is real (i.e. check ground truth).

  python scripts/verify_detections.py --clip ambient/lobby_bar2.mp4 --conf 0.4
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CLIPS_DIR = Path("eval/clips")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", required=True)
    ap.add_argument("--model", default="yolov8s.pt")
    ap.add_argument("--conf", type=float, default=0.4)
    ap.add_argument("--samples", type=int, default=8)
    args = ap.parse_args()

    from ultralytics import YOLO
    model = YOLO(args.model)

    path = CLIPS_DIR / args.clip
    cap = cv2.VideoCapture(str(path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    idxs = [int(total * (i + 0.5) / args.samples) for i in range(args.samples)]
    out_dir = Path("snapshots/verify") / Path(args.clip).stem
    out_dir.mkdir(parents=True, exist_ok=True)

    saved = 0
    for k, idx in enumerate(idxs):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, f = cap.read()
        if not ok or f is None:
            continue
        res = model(f, classes=[0], verbose=False)[0]
        if res.boxes is None or len(res.boxes) == 0:
            continue
        for b in res.boxes:
            c = float(b.conf[0])
            if c < args.conf:
                continue
            x1, y1, x2, y2 = map(int, b.xyxy[0])
            cv2.rectangle(f, (x1, y1), (x2, y2), (0, 0, 255), 2)
            cv2.putText(f, f"{c:.2f}", (x1, max(y1 - 6, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        p = out_dir / f"f{k}.jpg"
        cv2.imwrite(str(p), f)
        saved += 1
    cap.release()
    print(f"  saved {saved} annotated frames -> {out_dir.resolve()}")


if __name__ == "__main__":
    main()
