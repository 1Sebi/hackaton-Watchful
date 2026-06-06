# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Watchful turns a natural-language condition ("notify me when someone raises a hand in the jacuzzi") into a structured, checkable **Predicate**, then runs a continuous agent loop that perceives a live camera feed, reasons about it, and acts — **100% local** (Ollama VLM + YOLO + SQLite + localhost UI; no cloud, no API key). The differentiator is a **low false-trigger rate**, enforced by a five-mechanism anti-false-positive (AFP) layer; treat that reliability as a primary design constraint, not an afterthought.

## Commands

Windows/PowerShell is the primary environment (Python 3.13). The venv lives in `.venv`.

Dependencies are plain **pip** (`requirements.txt`) — no Poetry/pyproject/uv, no Makefile. YOLO/pose weights (`yolov8{n,s,m}.pt`, `yolov8n-pose.pt`) are **auto-downloaded** to the repo root on first run (gitignored), not committed. There is **no linting/formatting config** (ruff/black/eslint/prettier) and no CI/Docker — match surrounding style by hand.

```powershell
# First-time setup
python -m venv .venv; .\.venv\Scripts\activate
pip install -r requirements.txt

# Backend (FastAPI; agent loop starts as a background thread via lifespan)
.\.venv\Scripts\activate
uvicorn backend.main:app --reload        # -> http://localhost:8000/docs

# Frontend
cd frontend; npm install; npm run dev    # Vite dev server
npm run build                            # tsc + vite build

# Local VLM (required for compile + semantic conditions)
ollama pull moondream
ollama pull llama3.2-vision              # optional, heavy semantic conditions
```

### Tests

There is **no pytest**. Tests are standalone scripts run directly, each printing `RESULT: N/M checks passed` and exiting non-zero on failure. Run one with:

```powershell
python scripts/test_e2e.py        # full chain: NL -> compile -> eval -> AFP -> DB event
python scripts/test_compiler.py   # NL -> Predicate compilation
python scripts/test_evaluator.py  # predicate routing/evaluation
python scripts/test_antifalse.py  # the AFP gating layer
# also: test_detector, test_pose, test_vlm, test_tracker-ish, test_db, test_api, test_visualizer, test_reference, test_final
```

`scripts/` also holds non-test operational tools (`probe_rtsp.py`, `list_channels.py`, `record_clip.py`, `hikvision_io.py`, etc.) for working with real Hikvision cameras on-site.

### Eval

```powershell
python eval/run_eval.py --conf 0.5 --min-frames 2 --samples 8   # writes eval/results.md
```
Clips in `eval/clips/` are gitignored (real venue footage); `eval/ground_truth.json` is committed.

## Architecture

The pipeline is **`NL → Predicate → agent loop (PERCEIVE → REASON → AFP → ACT)`**. Read `docs/ARCHITECTURE.md` for the full diagram.

**Predicate** (`backend/predicates/types.py`) is the spine. The compiler emits it; the evaluator consumes it. Its `evaluator` field routes evaluation to one of: `yolo` (counts/zones/absence), `pose` (hand-raised/sitting/standing), `vlm` (semantic), or `hybrid`. `PredicateType` → default evaluator mapping lives in `EVALUATOR_BY_TYPE`. Unknown/ambiguous conditions fall back to `SEMANTIC` (a VLM visual question). The Predicate also carries the AFP thresholds (`min_confidence`, `min_consecutive`, `cooldown_seconds`).

**Hybrid is the core design decision** (`predicates/evaluator.py`): counts/zones/postures are deterministic and run on YOLO/pose at high FPS with no hallucination; the VLM is reserved for genuinely abstract conditions, throttled to ~1 FPS (`VLM_MAX_FPS`) and skipped when the scene hasn't changed. This is what keeps it cost-zero and reliable. Don't route a deterministic condition through the VLM.

**`CameraManager` (`backend/core/camera_manager.py`) is the live orchestrator** — this is where the real multi-camera agent loop runs, not `pipeline.py`. Key mechanics worth knowing before editing it:
- The whole venue is a grid; exactly **one room is "active"** at a time, and within it **only the single FOCUS camera** (`active_id`, the big "Live view") runs full per-frame detection. `is_active` = camera's room is open; `is_focus` = this is the one camera being detected. Cameras are grouped into rooms (`cameras.json` `room` field).
- **Focus-only detection:** the whole YOLO budget goes to the focus camera, so it detects smoothly (~9/s) regardless of how many cameras the room has (batching across all room cams used to crawl — 6 cams → ~1.6/s each). Non-focus cameras (active room or not) only get a light periodic people count (`_tile_count_tick`, ~every 8s); conditions evaluate on the focus camera. Switching focus = `set_active_room(room, primary_cam=...)`.
- **Heavy models are shared** across all cameras via `_Engine` (one detector, one pose, one VLM, one `threading.Lock`); per-camera state (tracker, AFP, motion gate, JPEG buffer, events) lives in each `CameraWorker`.
- **Display is decoupled from detection.** The render loop runs only for cameras in the active room (inactive ones idle), publishes its own latest frame + last-known boxes at `RENDER_FPS` (focus) / `GRID_TILE_FPS` (other tiles), and does **not** yield to detection — the detect loop runs in parallel and rate-caps itself at `DETECT_MAX_FPS`. (An old `engine.detecting` "skip publish while detecting" guard was removed; it throttled the feed to the detection rate and made video choppy.)
- **Asymmetric streaming:** only the focus camera opens the heavy 4K main stream (continuous); every other camera uses the light 360p sub-stream — opening 4K on multiple room cams at once starved/froze the non-focus grabbers. `switch_stream` does an atomic handoff (old source keeps feeding until the new one yields a real frame) to avoid black-gap flicker.
- **Tracker counts honestly:** `TrackManager.active_count` counts only tracks seen within `active_window` (~1.5s), not all tracks held for `prune_after` (5s) — otherwise fast detection on low-confidence (jittery) boxes mints short-lived ids and badly over-counts.
- This file is heavily perf-tuned for CPU-only boxes. The comments document *why* values are what they are. **Preserve these invariants** — many were regressions that got fixed. Watch the `[room-detect] SLOW cycle` log when changing detection cadence.

`backend/core/pipeline.py` (`AgentPipeline` / `get_pipeline()`) is the **legacy single-camera** loop. It's still referenced for VLM access and zone lookup by the condition compiler (`api/conditions.py`), so don't assume it's dead — but new live-detection logic belongs in `CameraManager`.

**Config flows through `backend/config.py`** (`settings` singleton). Note: the **committed `.env.example` values diverge from the in-code defaults** (e.g. `DETECTION_IMGSZ` 960 in `.env.example` vs 640 default in code; `DETECTION_MODEL` yolov8m). The code defaults reflect the current CPU-real-time tuning. Camera credentials are **never committed**: `backend/cameras.json` carries only `id/name/room/nvr/channel`; RTSP URLs are assembled at runtime from NVR IP/password in `.env` (`_build_rtsp`). Sub-stream channel `x02` → tiles, main `x01` → 4K active.

**Other layers** (one concern each):
- `core/`: `video_source` (webcam/RTSP/file, reconnect), `detector` (YOLOv8 + `detect_batch`), `tracker` (IoU/ByteTrack ids, per-id duration), `pose_analyzer` (COCO-17 keypoints + IoU association to tracks), `reference_frame` (`MotionGate` gates YOLO, `AdaptiveSampler` gates VLM).
- `antifalse/`: the five gates — `threshold`, `debouncer` (N consecutive), `cooldown` (+ zone mask, reference frame). Exposed as `AntiFalsePositive`.
- `actions/`: `dispatcher` (async) → `hikvision` (ISAPI relay), `webhook` (ntfy/Discord), `logger` (JSONL).
- `api/`: FastAPI routers (`cameras`, `rooms`, `conditions`, `zones`, `events`, `stream` = MJPEG, `ws` = WebSockets). `models/`: SQLAlchemy `Condition` / `Event` / `Zone`. `vlm/client.py`: Ollama OpenAI-compatible client, JSON mode.
- `frontend/`: React 18 + Vite + Tailwind; `HotelMap` (venue landing) → `RoomView` → `LiveView`/`CameraGrid`, plus `ConditionEditor`, `EventLog`, `ZoneDrawer`. State arrives via MJPEG stream + WebSocket events.

## Conventions

- A **Condition belongs to a camera** (`camera_id`); `null` = global (runs on every camera). Creating/editing a condition hot-reloads the affected worker(s) via `get_manager().reload(...)`.
- The compiler accepts **EN + RO** natural language (deterministic rules first, VLM fallback). README/docs mix Romanian and English — that's intentional.
- Build progress is logged step-by-step in `PROGRESS.md` (PAS 0 → 15); commit messages follow `type: summary` (`feat:`, `perf:`, `ui:`).
