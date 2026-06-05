# Watchful — Progress Log

## 📊 Current Status
- **Last completed step:** PAS 2 - VLM Client (Ollama + Moondream) ✅
- **Currently working on:** PAS 3 - YOLO Detector + Tracker
- **Last update:** 2026-06-05 19:40
- **Blockers:** none

## 🎯 Steps Overview

| # | Title | Status | Commit | Notes |
|---|---|---|---|---|
| 0 | Setup repo + Ollama + environment | ✅ DONE | 0dc20f4 | Py3.13, moondream+llama3.2-vision |
| 1 | Video Source abstraction | ✅ DONE | 883a47b | webcam 30.1 FPS (MSMF) |
| 2 | VLM Client (Ollama + Moondream) | ✅ DONE | bfdcf27 | warm ~246ms, tag v0.1 |
| 3 | YOLO Detector + Tracker | ⏳ TODO | - | - |
| 4 | Pose Analyzer | ⏳ TODO | - | - |
| 5 | Predicate Compiler (VLM-based) | ⏳ TODO | - | - |
| 6 | Predicate Evaluator (Hybrid) | ⏳ TODO | - | - |
| 7 | Reference Frame + Adaptive Sampling | ⏳ TODO | - | - |
| 8 | Anti-False-Positive Layer | ⏳ TODO | - | - |
| 9 | Database & Models | ⏳ TODO | - | - |
| 10 | Action Dispatcher + Hikvision | ⏳ TODO | - | - |
| 11 | FastAPI Backend + Pipeline | ⏳ TODO | - | - |
| 12 | Visualizer | ⏳ TODO | - | - |
| 13 | Frontend (React + Tailwind) | ⏳ TODO | - | - |
| 14 | Eval Set + Calibration | ⏳ TODO | - | - |
| 15 | Polish + Demo Prep | ⏳ TODO | - | - |

**Legend:** ⏳ TODO | 🚧 IN PROGRESS | ✅ DONE | ⚠️ BLOCKED | ⏭️ SKIPPED

## ✅ Step-by-Step Checklists

### PAS 0: Setup repo + Ollama + environment
**Status:** ✅ DONE
**Started:** 2026-06-05 19:10
**Commit:** 0dc20f4

Checklist:
- [x] Repo cloned local — `git clone` → exit 0, on `main`
- [x] Git identity configured — robertalc1 / robert.alcaziu@gmail.com (global)
- [x] Folder structure created — backend/{core,vlm,predicates,antifalse,actions,api,models}, frontend, eval/clips, scripts, docs
- [x] requirements.txt created
- [x] .gitignore created
- [x] .env.example created — incl. VLM_MODEL=moondream + VLM_MODEL_HEAVY=llama3.2-vision
- [x] README.md updated — full project README
- [x] **Ollama installed** — v0.30.5 (pre-installed, not reinstalled)
- [x] **Ollama service running** — PID 20848; `/api/tags` → 200
- [x] **Moondream pulled** — `ollama list` shows moondream:latest (1.7GB) + llama3.2-vision:latest (7.8GB)
- [x] **Ollama API test passed** — `/api/tags` 200 AND OpenAI-compat `/v1/chat/completions` 200, moondream returned `{"ok":true}` (JSON mode works)
- [x] Python venv created and activated — `.venv` Python 3.13.12
- [x] Python deps installed — `pip install -r requirements.txt` exit 0
- [x] Import test passed — cv2 4.13.0, ultralytics 8.4.60, torch 2.12.0+cpu, fastapi 0.136.3, numpy 2.4.6, openai 2.41.0 → ALL IMPORTS PASSED
- [x] PROGRESS.md created
- [x] First commit + push done — commit `0dc20f4`, pushed `2d37972..0dc20f4 main -> main` (exit 0)

**Notes:** torch is CPU-only (cuda=False) → may drop yolov8m→yolov8n in PAS 3 if FPS<15. Python 3.13 used (no 3.11 on machine); all ML wheels resolved fine.

### PAS 1: Video Source abstraction
**Status:** ✅ DONE
**Commit:** 883a47b

Checklist:
- [x] backend/core/video_source.py created
- [x] Supports int (webcam) source — runtime-tested, 30.1 FPS
- [x] Supports str (RTSP URL) source — file path runtime-tested (40/40 frames); RTSP backend (CAP_FFMPEG) wired, not stream-tested (no RTSP available)
- [x] Buffer size 1 — CAP_PROP_BUFFERSIZE=1
- [x] Reconnect logic (max 5 attempts) — _reconnect_and_read, file EOF guarded
- [x] width/height/fps properties
- [x] read() returns Optional[np.ndarray]
- [x] release() works — verified _cap is None after
- [x] Context manager — __enter__/__exit__
- [x] scripts/test_camera.py created
- [x] Test runs on webcam, FPS >= 15 — **30.1 FPS @ 640x480** PASS
- [x] Commit + push done

**Notes:** DSHOW webcam capped at 10 FPS (auto-exposure in indoor light) → switched Windows webcam backend to **MSMF** = 30.1 FPS at full 640x480, normal exposure. MJPG fourcc + buffersize 1 also set.

### PAS 2: VLM Client (Ollama + Moondream)
**Status:** ✅ DONE
**Commit:** bfdcf27

Checklist:
- [x] backend/vlm/__init__.py created
- [x] backend/vlm/client.py created
- [x] OllamaVLMClient class implemented
- [x] Base URL configurable (default localhost:11434, auto-appends /v1)
- [x] ask(image, question, schema) method works
- [x] JSON output mode enforced — response_format json_object + defensive _parse_json
- [x] Timeout handling (30s default)
- [x] Retry logic (1x retry on connection error) — APIConnectionError/APITimeoutError
- [x] Frame resize before sending (max 768px wide)
- [x] scripts/test_vlm.py created
- [x] Test: image + "how many people?" returns JSON answer — `{"count":0,"confidence":0.0}`
- [x] Latency measured and reported — **cold 277ms / warm 246ms**, health reachable
- [x] Tag v0.1-ollama-vlm created
- [x] Commit + push done

**Notes:** moundream warm latency ~250ms — excellent for the loop. moondream undercounts people (count via VLM weak) → counting routed to YOLO by design (PAS 3/6). heavy=True switches to llama3.2-vision for hard semantic conditions.

### PAS 3: YOLO Detector + Tracker
**Status:** ⏳ TODO

Checklist:
- [ ] backend/core/detector.py with PersonDetector
- [ ] Loads yolov8m.pt (or yolov8n.pt if CPU too slow)
- [ ] detect_and_track returns List[Detection]
- [ ] Uses model.track persist=True classes=[0]
- [ ] Verbose suppressed
- [ ] backend/core/tracker.py with TrackManager
- [ ] Positions deque, duration, prune, active_count
- [ ] Visual test: bboxes + IDs persist
- [ ] FPS >= 15 measured
- [ ] Commit + push done

### PAS 4: Pose Analyzer
**Status:** ⏳ TODO

Checklist:
- [ ] backend/core/pose_analyzer.py created
- [ ] Loads yolov8m-pose.pt
- [ ] COCO keypoints defined
- [ ] IoU association > 0.3 with detections
- [ ] is_hand_raised, is_sitting, is_standing implemented
- [ ] Edge cases: missing keypoints → False
- [ ] Visual test: skeleton overlay works
- [ ] Tag v0.2-detection created
- [ ] Commit + push done

### PAS 5: Predicate Compiler (VLM-based)
**Status:** ⏳ TODO

Checklist:
- [ ] backend/predicates/types.py with PredicateType enum + Predicate model
- [ ] backend/predicates/compiler.py created
- [ ] VLMPredicateCompiler class
- [ ] compile(text) → Predicate via Moondream (1 call, NO image, text-only)
- [ ] Returns: visual_question, predicate_type, evaluator (yolo|pose|vlm), params, thresholds
- [ ] Examples in prompt: 5-10 few-shot
- [ ] Test with 10 conditions: all compile successfully
- [ ] Bilingual (EN + RO) verified
- [ ] Commit + push done

### PAS 6: Predicate Evaluator (Hybrid)
**Status:** ⏳ TODO

Checklist:
- [ ] backend/predicates/evaluator.py created
- [ ] HybridEvaluator routes per predicate.evaluator field
- [ ] YOLO evaluator: count, presence, zone
- [ ] Pose evaluator: hand raised, sitting, standing
- [ ] VLM evaluator: complex semantic (sends crop to Ollama; heavy model for SEMANTIC)
- [ ] EvalResult dataclass
- [ ] Adaptive sampling: VLM apelat doar la 1 FPS, YOLO la 25 FPS
- [ ] Test: each evaluator type produces correct result
- [ ] Tag v0.3-agent-loop created
- [ ] Commit + push done

### PAS 7: Reference Frame + Adaptive Sampling
**Status:** ⏳ TODO

Checklist:
- [ ] backend/core/reference_frame.py created
- [ ] significant_change() method works
- [ ] Auto-update every 5 min
- [ ] Adaptive sampler: skip VLM calls when no significant change
- [ ] Test: empty scene → no VLM call (verify in logs)
- [ ] Commit + push done

### PAS 8: Anti-False-Positive Layer
**Status:** ⏳ TODO

Checklist:
- [ ] backend/antifalse/debouncer.py created
- [ ] backend/antifalse/cooldown.py created
- [ ] backend/antifalse/threshold.py created
- [ ] 5 mechanisms: debounce, threshold, cooldown, zone mask, reference frame
- [ ] Test: 100 noisy evals → max 1 trigger per cooldown
- [ ] Tag v0.4-anti-false-positive created
- [ ] Commit + push done

### PAS 9: Database & Models
**Status:** ⏳ TODO

Checklist:
- [ ] backend/database.py SQLAlchemy + SQLite
- [ ] backend/models/condition.py
- [ ] backend/models/event.py
- [ ] backend/models/zone.py
- [ ] CRUD verified via Python shell
- [ ] Commit + push done

### PAS 10: Action Dispatcher + Hikvision
**Status:** ⏳ TODO
(Reuse: salvage Hikvision ISAPI relay + Digest auth pattern from prior branch act.py, adapted local.)

Checklist:
- [ ] backend/actions/hikvision.py (Digest auth, ISAPI)
- [ ] relay_set(port, state, duration) works
- [ ] backend/actions/webhook.py (ntfy.sh, Discord, generic)
- [ ] backend/actions/logger.py
- [ ] backend/actions/dispatcher.py async coordinator
- [ ] scripts/test_hikvision_relay.py created
- [ ] docs/HIKVISION_ISAPI.md cheatsheet
- [ ] Tag v0.5-actions created
- [ ] Commit + push done

### PAS 11: FastAPI Backend + Pipeline
**Status:** ⏳ TODO

Checklist:
- [ ] backend/main.py with FastAPI app
- [ ] CORS configured
- [ ] backend/core/pipeline.py main agent loop
- [ ] /conditions CRUD endpoints
- [ ] /events endpoints
- [ ] /zones endpoints
- [ ] /stream/live.mjpg with overlay
- [ ] /ws/events WebSocket
- [ ] /ws/state WebSocket
- [ ] uvicorn starts, /docs accessible
- [ ] MJPEG stream visible in browser
- [ ] Commit + push done

### PAS 12: Visualizer
**Status:** ⏳ TODO

Checklist:
- [ ] backend/visualizer.py created
- [ ] Bbox colored per track_id
- [ ] Label "#ID Xs ✋" displayed
- [ ] Skeleton from COCO pairs
- [ ] Track trails alpha-fade
- [ ] Zone polygons semi-transparent
- [ ] HUD bar with stats
- [ ] MJPEG shows all overlays
- [ ] Commit + push done

### PAS 13: Frontend (React + Tailwind)
**Status:** ⏳ TODO

Checklist:
- [ ] Vite + React + TS scaffold
- [ ] Tailwind + shadcn installed
- [ ] LiveView component (MJPEG + canvas overlay)
- [ ] ConditionsList component
- [ ] ConditionEditor component (with compiled preview)
- [ ] EventLog component (WebSocket live)
- [ ] ZoneDrawer component (canvas polygon)
- [ ] StatusBar component
- [ ] End-to-end test: add condition → see trigger in log
- [ ] Tag v0.6-fullstack created
- [ ] Commit + push done

### PAS 14: Eval Set + Calibration
**Status:** ⏳ TODO

Checklist:
- [ ] Record 10 true clips + 10 trap + 10 neutral
- [ ] Label in eval/ground_truth.json
- [ ] eval/run_eval.py implemented
- [ ] Precision/recall/F1 computed
- [ ] Calibration: precision > 90%
- [ ] eval/results.md with concrete numbers
- [ ] Tag v0.9-eval-ready created
- [ ] Commit + push done

### PAS 15: Polish + Demo Prep
**Status:** ⏳ TODO

Checklist:
- [ ] README.md complete with screenshots
- [ ] docs/PITCH_NOTES.md with 5-min structure
- [ ] Demo rehearsed 3x with stopwatch
- [ ] Backup demo video 60s recorded
- [ ] Final test on webcam (2 conditions work)
- [ ] (If access) Final test on Hikvision
- [ ] Tag v1.0-demo-ready created
- [ ] Commit + push done

## 📝 Activity Log
- 2026-06-05 19:10 | PAS 0 | Started setup; cloned repo, inspected main (only README) + prior branch
- 2026-06-05 19:12 | PAS 0 | Prior branch `claude/busy-hawking-MlsZS` is CLOUD-based (anthropic API + Streamlit) → incompatible with zero-cloud promise; NOT used. Salvageable patterns noted for PAS 8/10.
- 2026-06-05 19:14 | PAS 0 | Created folder structure + requirements/gitignore/env.example/README
- 2026-06-05 19:16 | PAS 0 | venv Python 3.13.12 created; deps installed (exit 0)
- 2026-06-05 19:17 | PAS 0 | Import test PASSED (cv2/ultralytics/torch/fastapi/openai/ollama)
- 2026-06-05 19:18 | PAS 0 | PROGRESS.md created
- 2026-06-05 19:20 | PAS 0 | ✅ DONE — committed 0dc20f4, pushed to main (16/16). Write access to repo CONFIRMED.
- 2026-06-05 19:25 | PAS 1 | Built VideoSource; webcam initially 10 FPS (DSHOW auto-exposure) → fixed via MSMF backend = 30.1 FPS
- 2026-06-05 19:30 | PAS 1 | ✅ DONE — webcam 30.1 FPS, file 40/40 frames; committed 883a47b
- 2026-06-05 19:40 | PAS 2 | ✅ DONE — OllamaVLMClient, visual Q→JSON, warm 246ms; committed bfdcf27, tag v0.1-ollama-vlm

## 🎓 Decision Log
- **VLM model:** moondream (primary, fast, 1.7GB) + llama3.2-vision (fallback for hard SEMANTIC, 7.8GB). Replaces brief's `llava:7b` suggestion — both already pulled locally. User-approved.
- **Python 3.13** instead of brief's 3.11 (machine has only 3.13/3.14). All ML wheels (torch 2.12, ultralytics 8.4.60, opencv 4.13) resolved cleanly. User-approved. Avoided 3.14 (wheel risk).
- **torch CPU-only** (cuda=False) — laptop has no configured CUDA. Plan: keep yolov8m; if PAS 3 FPS<15 on CPU, downgrade to yolov8n.
- **Prior branch not reused as base** — it was a cloud (Anthropic API) prototype. Kept on its own branch; we build the brief's local `backend/` architecture on `main`. Will borrow its Hikvision ISAPI (act.py) + debounce/cooldown patterns, adapted.
- **Ollama via HTTP** — app does not require `ollama` on PATH (uses localhost:11434). CLI checks use full exe path.
- **Repo layout** — cloned into `Desktop/Hack/hackaton-Watchful/`; work happens inside the repo.

## 💡 Ideas (out of scope)
- (nimic)

## ⚠️ Blockers
- (nimic)
