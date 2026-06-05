# ✋ End-to-end hand-raise demo — WORKING on real hardware

> Hardware-lane result. The full Perceive→Understand→Act loop was run live against
> a real ThePlace camera with a real person and a real phone notification. This is
> the flagship demo from the brief, proven on the actual venue system (not webcam,
> not bus.jpg). The cloud session cannot reproduce this — no camera access.

## What works ✅

```
Real Hikvision 4K camera (NVR1 cam5, restaurant)
   → YOLOv8m-pose detects "a hand raised above the shoulder"
      → ntfy.sh push notification on the phone
```
Live run: person raised a hand → detected → phone buzzed. Confirmed on device.
Proof frames saved to snapshots/handraise_live/detect_*.jpg (gitignored).

## Two findings that cost us time (so the team doesn't repeat them)

### 1. Pose/gesture detection NEEDS the 4K main stream + large imgsz
On the **sub-stream (640x360)** the model reliably detected *people* but **never**
the hand-raise gesture (0/N), even at low keypoint-confidence — a distant person's
wrist is only a few pixels, so the keypoint is unusable. Switching to the **main
stream (3840x2160) with `imgsz=1280`** → hand-raise detected immediately (13/13 in
one run).
- **Rule:** presence/count → sub-stream is fine (fast). **Pose/gesture on distant
  subjects → main stream + imgsz≥1280.** This contradicts a blanket "use sub-stream
  for detection" default.
- Cost: 4K + imgsz1280 + yolov8m-pose on CPU ≈ 0.5 FPS. Fine for a triggered demo;
  for production, crop the ROI and run the crop at full res, or use a GPU.

### 2. Emoji in an HTTP header silently kills the notification
`requests.post(..., headers={"Title": "👋 Watchful..."})` raises
`UnicodeEncodeError: 'latin-1' codec can't encode` — HTTP headers must be latin-1.
The exception was swallowed and **no notification was ever sent**, while manual
ASCII-only tests worked — very confusing to debug.
- **Fix:** keep the `Title` header ASCII; put the emoji in **Tags** (ntfy renders it
  as an icon) and in the utf-8 **body**. Applies to any webhook action in PAS 10.

### 3. ntfy.sh free tier rate-limits bursts
13 notifications in 45s → most dropped (POST returns 200, delivery throttled). Space
them out (cooldown ≥ 10-15s) or self-host ntfy. One clear alert per event is better
for a demo anyway.

## Recommended demo config
```
camera   : NVR1 cam5 main stream (or any camera the subject is reasonably close to)
model    : yolov8m-pose.pt, imgsz=1280, kp_conf=0.3
trigger  : wrist above shoulder, debounce, cooldown 15s
action   : ntfy.sh push (ASCII title + Tags emoji)   # no relay wiring needed
```

## Reproduce
```
python scripts/watch_handraise_camera.py --ip <nvr> --password <pw> --cam 5 \
   --stream main --imgsz 1280 --model yolov8m-pose.pt --kp-conf 0.3 \
   --cooldown 15 --ntfy <your-topic>
```
Needs `imgsz` support in `backend/core/pose_analyzer.py` — add an `imgsz` arg to
`PoseAnalyzer.__init__` and pass it to `self.model(frame, imgsz=...)`. Relay action
also available via `--fire-nvr NVR2 --fire-output 1` (validated; see HIKVISION_RELAY.md).
```
