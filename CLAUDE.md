# CLAUDE.md

Guidance for Claude Code sessions on this repo.

## What this is

The Watcher turns a natural-language condition ("notify me when someone raises a hand in the jacuzzi") into a structured, checkable **Predicate**, then runs a continuous agent loop that perceives a live camera feed, reasons about it, and acts — **100% local** (Ollama VLM + YOLO + SQLite + localhost UI; no cloud, no API key). The differentiator is a **low false-trigger rate**, enforced by a five-mechanism anti-false-positive (AFP) layer; treat that reliability as a primary design constraint, not an afterthought.

## Commands

Primary environment: Python 3.13, Node 18+. The venv lives in `.venv`.

Dependencies are plain **pip** (`requirements.txt`) — no Poetry/pyproject/uv, no Makefile. YOLO/pose weights (`yolov8m.pt`, `yolov8n-pose.pt`) auto-download to the repo root on first run (gitignored), not committed. No linter/formatter config; no CI/Docker — match surrounding style by hand.

```bash
# First-time setup
python -m venv .venv && source .venv/bin/activate   # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt

# Backend (FastAPI; agent loop starts as a background thread via lifespan)
uvicorn backend.main:app --reload                   # -> http://localhost:8000/docs

# Frontend
cd frontend && npm install && npm run dev           # Vite dev server
npm run build                                       # tsc + vite build

# Local VLM (required for compile + semantic conditions)
ollama pull moondream
ollama pull llama3.2-vision                         # optional, hard-semantic conditions
```

### Tests

Tests are standalone scripts run directly (no pytest), each printing `RESULT: N/M checks passed` and exiting non-zero on failure.

```bash
python scripts/test_e2e.py        # full chain: NL -> compile -> eval -> AFP -> DB event
python scripts/test_compiler.py
python scripts/test_evaluator.py
python scripts/test_antifalse.py
# also: test_detector, test_pose, test_vlm, test_db, test_api, test_visualizer, test_reference, test_final
```

`scripts/` also holds operational tools — `probe_rtsp.py`, `list_channels.py`, `hikvision_io.py` (relay), `record_clip.py`, and especially `audit_streams.py` / `upgrade_substreams.py` / `restore_substreams.py` for the Hikvision sub-stream reconfiguration that gates detection quality.

### Eval

```bash
python eval/run_eval.py --conf 0.5 --min-frames 2 --samples 8   # writes eval/results.md
```

Clips in `eval/clips/` are gitignored (real venue footage); `eval/ground_truth.json` is committed.

## Architecture

`NL → Predicate → agent loop (PERCEIVE → REASON → AFP → ACT)`.

### The Predicate spine

**`backend/predicates/types.py`** defines `PredicateType` (COUNT_GT, PRESENCE_IN_ZONE, ABSENCE_FOR_DURATION, POSE_HAND_RAISED/SITTING/STANDING, SEMANTIC, …) plus `Predicate` itself. The `evaluator` field routes to one of: `yolo` (counts/zones/absence), `pose` (postures), `vlm` (semantic), `hybrid`. `EVALUATOR_BY_TYPE` is the default mapping. Unknown/ambiguous conditions fall back to SEMANTIC (a VLM visual question). Each Predicate also carries the AFP thresholds (`min_confidence`, `min_consecutive`, `cooldown_seconds`).

**Compiler** (`predicates/compiler.py`): deterministic EN+RO rules first; VLM fallback only as a safety net for genuinely abstract conditions. Don't route a deterministic condition through the VLM.

**Hybrid evaluator** (`predicates/evaluator.py`): counts/zones/postures are deterministic and run on YOLO/pose at high FPS with no hallucination; the VLM is reserved for genuinely abstract conditions, throttled to ~1 FPS (`VLM_MAX_FPS`) and skipped when the scene hasn't changed (reference-frame gate). This is what keeps it cost-zero AND reliable.

### `CameraManager` — invariants in `backend/core/camera_manager.py`

Read the docstring at the top of that file: it codifies the rules below. **Don't break them in future changes.**

1. **EXACTLY ONE stream per camera.** Each `CameraWorker` opens the sub-stream URL and never switches. There is no main_url, no switch_stream. To raise detection quality, reconfigure the NVR sub profile with `scripts/upgrade_substreams.py` — the app consumes the same single feed.
2. **EXACTLY ONE loop per camera (`_loop`).** It decodes a frame, runs YOLO + tracking + condition evaluation, draws the overlay, publishes the JPEG. Display and detection are the same operation at the same rate — the boxes the viewer sees are the boxes that just got computed on that frame. Visible cameras run as fast as decode + lock-serialized YOLO allow; off-screen rule cameras run the same body capped at `MONITOR_FPS` so they don't steal CPU from what the user is watching.
3. **One detector + one pose + one VLM** in `_Engine`, shared by every worker; `engine.lock` serializes inference (ultralytics is not thread-safe). Per-camera state (tracker, AFP, motion gate, JPEG buffer, events) lives in each `CameraWorker`.
4. **VideoSource is `continuous=False`** — no background grabber; an idle camera (no rules, not active) decodes zero frames.

State surfaces: `is_active` = camera's room is the one the user is viewing; `is_focus` = the big-view camera within that room. The focus camera publishes a *clean* JPEG (boxes drawn by the frontend overlay via the `/track` REST snapshot of `_last_dets`); other room tiles get a light name+motion-dot overlay.

`backend/core/pipeline.py` (`AgentPipeline` / `get_pipeline()`) is the **legacy single-camera** loop. It's still referenced for VLM access and zone lookup by the condition compiler (`api/conditions.py`), so don't assume it's dead — but all new live-detection logic belongs in `CameraManager`.

### Config

**`backend/config.py`** (`settings` singleton). Camera credentials are **never committed**: `backend/cameras.json` carries only `id/name/room/nvr/channel`; RTSP URLs are assembled at runtime from NVR IP/password in `.env` (`_build_rtsp`). The single stream is the sub-stream — channel `x02`.

Optional `ENABLED_ROOMS=Restaurant,Jacuzzi,...` in `.env` whitelists which rooms' cameras get loaded.

Two engine knobs:
- `MONITOR_FPS` — rate cap for off-screen rule cameras (default 1.5)
- `MOTION_MIN_PCT` — % of pixels that must change to flag the scene as moving (drives VLM gating + the tile "live" dot)

### Other layers

- `core/`: `video_source` (RTSP/webcam/file, reconnect), `detector` (YOLOv8), `tracker` (ByteTrack + IoU per-camera tracking), `pose_analyzer` (COCO-17 keypoints + IoU association), `reference_frame` (`MotionGate` gates YOLO, `AdaptiveSampler` gates VLM), `pin_tracker` (records the path of a clicked person to MP4).
- `antifalse/`: the five gates — `threshold`, `debouncer` (N consecutive), `cooldown` (+ zone mask, reference frame). Exposed as `AntiFalsePositive`.
- `actions/`: `dispatcher` (async) → `hikvision` (ISAPI relay), `messaging` (Telegram bot, WhatsApp via CallMeBot), `webhook` (ntfy/Discord/generic), `logger` (JSONL).
- `api/`: FastAPI routers (`cameras`, `rooms`, `conditions`, `zones`, `events`, `stream` = MJPEG, `ws` = WebSockets). `models/`: SQLAlchemy `Condition` / `Event` / `Zone`. `vlm/client.py`: Ollama OpenAI-compatible client, JSON mode.
- `frontend/`: React 18 + Vite + Tailwind. `HotelMap` (venue landing) → `RoomView` → `LiveView`/`CameraGrid`, plus `Dashboard`, `ConditionEditor`, `EventLog`/`EventFeed`, `ZoneDrawer`. State arrives via MJPEG + WebSocket.

## Conventions

- A **Condition belongs to a camera** (`camera_id`); `null` = runs on every camera. Creating/editing a condition hot-reloads the affected worker(s) via `get_manager().reload(...)`.
- The compiler accepts **EN + RO** natural language (deterministic rules first, VLM fallback). README/docs mix Romanian and English — intentional.
- Commit messages follow `type: summary` (`feat:`, `perf:`, `fix:`, `refactor:`).
