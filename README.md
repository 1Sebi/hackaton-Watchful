# Watchful

> **Hack A Ton 2026 · ThePlace Camera Agent (Track 2).**
> Tell the camera what to watch — in plain language — and it acts. 100% local.

A real venue (hotel) carries 21 Hikvision cameras across 2 NVRs. Watchful gives
each room a self-service AI agent: write a rule like *"more than 10 people in
the event hall → notify me"* or *"someone raises a hand in the jacuzzi → relay
1 on for 5 minutes"*, and it runs continuously — no cloud, no API key, no
recurring cost.

The hard part isn't spotting people. It's **not firing on shadows.**

---

## What it does

- **Multi-camera grid** with one *active room*. The user opens a room from the
  venue map; every camera in that room runs detection at the rate the viewer
  sees the feed — the boxes on screen are computed on the frame on screen.
- **Plain-language rules.** A deterministic compiler (EN + RO) handles counts /
  zones / postures / absence; anything more abstract ("looks distressed") falls
  back to a local VLM (Ollama).
- **Five actions:** Hikvision ISAPI relay (with duration), ntfy.sh phone push,
  Telegram (bot text + clip), WhatsApp (CallMeBot), generic webhook, JSONL log.
- **Pin-to-track.** Click a person in the live view; the agent records their
  annotated path until you press Stop & send → MP4 to Telegram.
- **Anti-false-positive:** confidence threshold, N-consecutive debounce,
  cooldown, zone mask, and reference-frame gating. Tested 100% precision on the
  trap clips in `eval/`.

## What's local

| | |
|---|---|
| VLM | Ollama + Moondream (heavy: llama3.2-vision) |
| Detection | YOLOv8 (Ultralytics) |
| Pose | YOLOv8-pose |
| Backend | FastAPI on localhost |
| Frontend | React + Vite on localhost |
| Storage | SQLite file |
| Camera | RTSP from local Hikvision NVR |
| Cloud APIs | **none** |

---

## Run it

Prereqs: Python 3.13, Node 18+, [Ollama](https://ollama.com).

```bash
# 1. pull the local VLM (once)
ollama pull moondream
ollama pull llama3.2-vision   # optional, hard-semantic conditions

# 2. backend
python -m venv .venv && source .venv/bin/activate   # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                 # set NVR creds + notifier tokens
uvicorn backend.main:app --reload                    # → http://localhost:8000/docs

# 3. frontend
cd frontend && npm install && npm run dev
```

YOLO weights (`yolov8m.pt`, `yolov8n-pose.pt`) auto-download into the repo root
on first run.

---

## Architecture

```
       user types a rule in the dashboard
                  │
                  ▼
   COMPILER  (predicates/compiler.py)
   EN+RO deterministic rules ─▶ structured Predicate
   else ─▶ local VLM ─▶ SEMANTIC predicate

   (Condition + Predicate stored in SQLite)
                  │
                  ▼
      ONE LOOP PER CAMERA (core/camera_manager.py)
      ─────────────────────────────────────────
      decode frame ─▶ YOLO + ByteTrack ─▶ Pose (only when a pose rule is on)
                    ─▶ HybridEvaluator (yolo / pose / vlm)
                    ─▶ AntiFalsePositive (threshold · debounce · cooldown · zone · reference frame)
                    ─▶ ActionDispatcher (relay / ntfy / telegram / whatsapp / webhook / log)
                    ─▶ draw overlay + publish JPEG
```

Hard-coded invariants in `camera_manager.py` (don't break in future changes):

1. **One stream per camera.** The (upgraded) sub-stream is the single source —
   no main/sub toggle. Reconfigure that profile via
   `scripts/upgrade_substreams.py` if quality isn't enough.
2. **One loop per camera.** The same loop decodes, detects, evaluates, draws,
   and publishes. Detection and display run at the same rate on the same
   frames — the boxes the viewer sees are the ones just computed.
3. **Off-screen rule cameras still detect**, capped at `MONITOR_FPS`, so a
   rule like *"jacuzzi hand raised"* fires while you're viewing the lobby.
4. **One YOLO + one pose + one VLM** in `_Engine`, serialized across workers.

## Why hybrid (not pure-VLM)

Counts, zones, postures are deterministic — YOLO/Pose answer at high FPS with
zero hallucination. The VLM is reserved for genuinely abstract conditions and
throttled to ≤1 FPS, skipped entirely when the scene hasn't changed. This is
what keeps it cost-zero AND reliable.

---

## Layout

```
backend/
  core/        video_source · detector · tracker · pose · reference_frame ·
               camera_manager (the loop) · pin_tracker
  vlm/         Ollama client (OpenAI-compatible)
  predicates/  types · NL→Predicate compiler · HybridEvaluator
  antifalse/   threshold · debouncer · cooldown
  actions/     dispatcher · hikvision (ISAPI relay) · messaging (Telegram/WhatsApp) ·
               webhook · logger
  api/         cameras · rooms · conditions · zones · events · stream (MJPEG) · ws
  models/      Condition · Event · Zone (SQLAlchemy)
frontend/      React + Vite + Tailwind (HotelMap → RoomView → LiveView)
scripts/       audit_streams · upgrade_substreams · restore_substreams · test_*
docs/          HIKVISION_ISAPI · HIKVISION_RELAY
eval/          ground_truth.json · run_eval.py · results.md
```

## Sub-stream upgrade (one-time per venue)

YOLO resizes everything to `imgsz=640` internally — there is no detection
benefit to feeding it 4K. The bottleneck on a CPU-only laptop is H.264 decode.
The sub-stream is therefore the only stream the app consumes, and a small
helper reconfigures each camera's NVR sub profile to detection-grade quality
once:

```bash
python scripts/audit_streams.py --probe        # see what's configured now
python scripts/upgrade_substreams.py --dry-run # preview the change
python scripts/upgrade_substreams.py           # apply (default: 1280x720, 15fps, ~2 Mbps H.264)
python scripts/audit_streams.py --probe        # verify
# rollback if needed:
python scripts/restore_substreams.py
```

This is what unlocks "detection on many cameras simultaneously" on a single
laptop.
