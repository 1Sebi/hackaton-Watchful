"""Watch a real NVR camera for a hand-raise and react — headless (no window),
so the person can be at the venue, not at the laptop.

Runs YOLOv8-pose on the live feed, detects 'a hand raised above the shoulder'
with a debounce, saves an annotated proof frame on each detection, and prints
events. Optionally fires an NVR relay on detection (the full Act loop).

  python scripts/watch_handraise_camera.py --ip 192.168.0.59 --password "..." --cam 5 --seconds 40
  # full loop (also fire NVR2 relay 1 on detection):
  python scripts/watch_handraise_camera.py ... --fire-nvr NVR2 --fire-output 1
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;8000000")

import cv2

from backend.core.pose_analyzer import PoseAnalyzer, draw_skeleton

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


def notify_ntfy(topic, title, message):
    # HTTP headers must be latin-1 — emoji in Title raises UnicodeEncodeError and
    # the message silently never sends. Keep Title ASCII; emoji goes via Tags
    # (rendered as an icon by ntfy) and in the utf-8 body.
    import requests
    title_ascii = title.encode("ascii", "ignore").decode().strip() or "Watchful"
    try:
        r = requests.post(f"https://ntfy.sh/{topic}",
                          data=message.encode("utf-8"),
                          headers={"Title": title_ascii, "Priority": "high",
                                   "Tags": "wave"},
                          timeout=8)
        if r.status_code != 200:
            print(f"  ntfy HTTP {r.status_code}: {r.text[:120]}", flush=True)
    except Exception as e:
        print(f"  ntfy error: {e}", flush=True)


def fire_relay(env, nvr, output, seconds=2.0):
    import requests
    from requests.auth import HTTPDigestAuth
    ip = env[f"{nvr}_IP"]; auth = HTTPDigestAuth("admin", env[f"{nvr}_PASS"])
    url = f"http://{ip}:80/ISAPI/System/IO/outputs/{output}/trigger"
    for st in ("high", "low"):
        requests.put(url, auth=auth,
                     data=f"<IOPortData><outputState>{st}</outputState></IOPortData>",
                     timeout=8)
        if st == "high":
            time.sleep(seconds)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--cam", type=int, default=5)
    ap.add_argument("--stream", choices=["main", "sub"], default="sub")
    ap.add_argument("--model", default="yolov8m-pose.pt")
    ap.add_argument("--seconds", type=float, default=40.0)
    ap.add_argument("--hits", type=int, default=2, help="consecutive detections to fire")
    ap.add_argument("--cooldown", type=float, default=3.0)
    ap.add_argument("--fire-nvr", default=None, help="NVR1|NVR2 to fire a relay on detect")
    ap.add_argument("--fire-output", type=int, default=1)
    ap.add_argument("--ntfy", default=None, help="ntfy.sh topic to notify on detect")
    ap.add_argument("--debug", action="store_true", help="save periodic annotated diag frames")
    ap.add_argument("--kp-conf", type=float, default=0.35, help="keypoint confidence threshold")
    ap.add_argument("--imgsz", type=int, default=None, help="inference size (e.g. 1280 for 4K)")
    args = ap.parse_args()

    analyzer = PoseAnalyzer(model_path=args.model, kp_conf=args.kp_conf, imgsz=args.imgsz)
    env = load_env()

    chan = args.cam * 100 + (1 if args.stream == "main" else 2)
    url = (f"rtsp://admin:{quote(args.password, safe='')}@{args.ip}:554"
           f"/Streaming/Channels/{chan}")
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print("FAILED to open stream"); sys.exit(2)

    out_dir = Path("snapshots/handraise_live"); out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Watching {args.ip} cam{args.cam} for {args.seconds:.0f}s — "
          f"STAND IN VIEW AND RAISE A HAND. (model={args.model})")
    streak = last_fire = fires = frames = ppl_seen = 0
    last_fire = 0.0
    t_end = time.time() + args.seconds
    while time.time() < t_end:
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        frames += 1
        people = analyzer.analyze(frame)
        ppl_seen = max(ppl_seen, len(people))
        raised, which = False, ""
        for p in people:
            r, w = analyzer.is_hand_raised(p.keypoints, "shoulder")
            if r:
                raised, which = True, w
                break
        if raised:
            print(f"  raised@frame{frames} ({which})", flush=True)
            # periodic diagnostic frame (every ~2.5s): skeleton + per-person raised status
        if args.debug and frames % 25 == 0 and people:
            dbg = frame.copy()
            for p in people:
                draw_skeleton(dbg, p.keypoints, 0.35)
                r, w = analyzer.is_hand_raised(p.keypoints, "shoulder")
                x1, y1 = int(p.bbox[0]), int(p.bbox[1])
                lab = f"RAISED:{w}" if r else "down"
                col = (0, 230, 0) if r else (200, 200, 200)
                cv2.putText(dbg, lab, (x1, max(y1 - 6, 14)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
            dbgfn = out_dir / f"diag_{frames}.jpg"
            cv2.imwrite(str(dbgfn), dbg)

        streak = streak + 1 if raised else 0
        if streak >= args.hits and (time.time() - last_fire) >= args.cooldown:
            fires += 1
            last_fire = time.time()
            # save annotated proof frame
            for p in people:
                draw_skeleton(frame, p.keypoints, 0.4)
            cv2.putText(frame, f"HAND RAISED ({which})", (15, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 230, 0), 2)
            fn = out_dir / f"detect_{fires}.jpg"
            cv2.imwrite(str(fn), frame)
            msg = f"  [{time.strftime('%H:%M:%S')}] HAND RAISED #{fires} ({which}) -> {fn.name}"
            if args.fire_nvr:
                fire_relay(env, args.fire_nvr, args.fire_output)
                msg += f" + fired {args.fire_nvr} relay {args.fire_output}"
            if args.ntfy:
                notify_ntfy(args.ntfy, "👋 Watchful: hand raised!",
                            f"Detected {which} on camera {args.cam} (real feed) "
                            f"at {time.strftime('%H:%M:%S')}")
                msg += f" + ntfy:{args.ntfy}"
            print(msg, flush=True)
    cap.release()
    print(f"Done. {frames} frames, max {ppl_seen} people seen, {fires} hand-raises detected.")


if __name__ == "__main__":
    main()
