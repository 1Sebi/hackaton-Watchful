# Watchful — Progress Log

## 📊 Current Status
- **Last completed step:** PAS 11 - FastAPI Backend + Pipeline ✅
- **Currently working on:** PAS 12 - Visualizer
- **Last update:** 2026-06-05 21:25
- **Blockers:** none

## 🎯 Steps Overview

| # | Title | Status | Commit | Notes |
|---|---|---|---|---|
| 0 | Setup repo + Ollama + environment | ✅ DONE | 0dc20f4 | Py3.13, moondream+llama3.2-vision |
| 1 | Video Source abstraction | ✅ DONE | 883a47b | webcam 30.1 FPS (MSMF) |
| 2 | VLM Client (Ollama + Moondream) | ✅ DONE | bfdcf27 | warm ~246ms, tag v0.1 |
| 3 | YOLO Detector + Tracker | ✅ DONE | 7e8103d | yolov8n 31.9 FPS, bus 3 persons |
| 4 | Pose Analyzer | ✅ DONE | 672798a | 3 standing, rules 9/9, tag v0.2 |
| 5 | Predicate Compiler (VLM-based) | ✅ DONE | c97b346 | 10/10 EN+RO, hybrid |
| 6 | Predicate Evaluator (Hybrid) | ✅ DONE | bafac94 | 11/11 checks, tag v0.3 |
| 7 | Reference Frame + Adaptive Sampling | ✅ DONE | cd84065 | 5/5, empty→no VLM |
| 8 | Anti-False-Positive Layer | ✅ DONE | 64529aa | 4/4, max 1/cooldown, tag v0.4 |
| 9 | Database & Models | ✅ DONE | b0a65bb | CRUD 6/6 |
| 10 | Action Dispatcher + Hikvision | ✅ DONE | 2489aae | 8/8 stand-in, tag v0.5 |
| 11 | FastAPI Backend + Pipeline | ✅ DONE | 287d4a6 | live+TestClient 12/12 |
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
**Status:** ✅ DONE
**Commit:** 7e8103d

Checklist:
- [x] backend/core/detector.py with PersonDetector
- [x] Loads yolov8n.pt — **yolov8m=2 FPS on CPU (unusable) → yolov8n=31.9 FPS**
- [x] detect_and_track returns List[Detection]
- [x] Uses model.track persist=True classes=[0]
- [x] Verbose suppressed
- [x] backend/core/tracker.py with TrackManager
- [x] Positions deque, duration, prune, active_count — deterministic test passed
- [x] Visual test: bboxes + IDs persist — bus.jpg 3 persons (0.83-0.87), annotated image verified, ids {1,2,3} stable across 5 frames
- [x] FPS >= 15 measured — **31.9 FPS** on webcam
- [x] Commit + push done

**Notes:** Default model → yolov8n.pt (CPU). Visual person test uses Ultralytics' bundled ASSETS/bus.jpg (local, zero network). Annotated proof at eval/screenshots/detector_bus.jpg (gitignored).

### PAS 4: Pose Analyzer
**Status:** ✅ DONE
**Commit:** 672798a

Checklist:
- [x] backend/core/pose_analyzer.py created
- [x] Loads yolov8n-pose.pt (CPU; brief's yolov8m-pose too slow)
- [x] COCO keypoints defined — COCO_KEYPOINTS + KP_INDEX + COCO_SKELETON
- [x] IoU association > 0.3 with detections — associate(), 3/3 on bus.jpg
- [x] is_hand_raised, is_sitting, is_standing implemented — geometric rules
- [x] Edge cases: missing keypoints → False — verified (missing.no_* all OK)
- [x] Visual test: skeleton overlay works — eval/screenshots/pose_bus.jpg verified
- [x] Tag v0.2-detection created
- [x] Commit + push done

**Notes:** bus.jpg → 3 poses all standing; 9/9 deterministic rule checks; pose 31.5 FPS on webcam.

### PAS 5: Predicate Compiler (VLM-based)
**Status:** ✅ DONE
**Commit:** c97b346

Checklist:
- [x] backend/predicates/types.py with PredicateType enum + Predicate model
- [x] backend/predicates/compiler.py created
- [x] VLMPredicateCompiler class
- [x] compile(text) → Predicate via VLM (text-only, 1 call on compile_heavy path) — verified llama3.2-vision routed "empty for half a minute" → ABSENCE_FOR_DURATION
- [x] Returns: visual_question, predicate_type, evaluator (yolo|pose|vlm), params, thresholds
- [x] Examples in prompt: 7 few-shot (5-10 ✓)
- [x] Test with 10 conditions: all compile successfully — **10/10**
- [x] Bilingual (EN + RO) verified — 3 RO cases pass
- [x] Commit + push done

**Notes:** HYBRID design (Decision Log) — deterministic EN+RO rules first (instant, reliable), templated SEMANTIC fallback. moondream too unreliable as a *text* compiler (hallucinates structural types) → not trusted for routing by default; structural VLM override only on compile_heavy (llama3.2-vision). Caught via re-run discipline (8/10 regression spotted, fixed → 10/10).

### PAS 6: Predicate Evaluator (Hybrid)
**Status:** ✅ DONE
**Commit:** bafac94

Checklist:
- [x] backend/predicates/evaluator.py created
- [x] HybridEvaluator routes per predicate.evaluator field
- [x] YOLO evaluator: count, presence, zone — + absence-for-duration
- [x] Pose evaluator: hand raised, sitting, standing
- [x] VLM evaluator: complex semantic (full-frame default, crop via params; heavy opt-in) — bus.jpg "is there a bus?"→True
- [x] EvalResult dataclass — + EvalContext per-frame bundle
- [x] Adaptive sampling: VLM throttled to vlm_max_fps (per-predicate cache); YOLO/Pose every frame — verified cached <1s, fresh after
- [x] Test: each evaluator type produces correct result — **11/11 checks**
- [x] Tag v0.3-agent-loop created
- [x] Commit + push done

**Notes:** semantic VLM uses moondream by default (fast ~250ms); heavy=True (llama3.2-vision) opt-in via params. point-in-zone via cv2.pointPolygonTest.

### PAS 7: Reference Frame + Adaptive Sampling
**Status:** ✅ DONE
**Commit:** cd84065

Checklist:
- [x] backend/core/reference_frame.py created
- [x] significant_change() method works — blurred-gray %-changed-pixels diff
- [x] Auto-update every 5 min — update_interval=300s default (verified at 10s in test)
- [x] Adaptive sampler: skip VLM calls when no significant change — AdaptiveSampler.should_run_vlm
- [x] Test: empty scene → no VLM call — static 10 frames = [True, False×9]
- [x] Commit + push done

**Notes:** 5/5 checks. Forced periodic VLM (force_interval) ensures occasional semantic checks even on a static scene.

### PAS 8: Anti-False-Positive Layer
**Status:** ✅ DONE
**Commit:** 64529aa

Checklist:
- [x] backend/antifalse/debouncer.py created
- [x] backend/antifalse/cooldown.py created
- [x] backend/antifalse/threshold.py created
- [x] 5 mechanisms: debounce, threshold, cooldown (+ zone mask in evaluator PAS6, reference frame PAS7) — AntiFalsePositive coordinator
- [x] Test: 100 noisy evals → max 1 trigger per cooldown — fires [2,32,66,99], gaps all ≥30s
- [x] Tag v0.4-anti-false-positive created
- [x] Commit + push done

**Notes:** 4/4 checks. threshold blocks low-conf, debounce needs N consecutive, happy path fires once then mutes.

### PAS 9: Database & Models
**Status:** ✅ DONE
**Commit:** b0a65bb

Checklist:
- [x] backend/database.py SQLAlchemy + SQLite — engine/SessionLocal/init_db/get_db
- [x] backend/models/condition.py — text + predicate(JSON) + action(JSON) + enabled
- [x] backend/models/event.py — condition_id FK, detected/confidence/reason/action_taken/snapshot
- [x] backend/models/zone.py — name + polygon(JSON)
- [x] CRUD verified via Python shell — **6/6** (create/read/json-roundtrip/fk/update/delete)
- [x] Commit + push done

### PAS 10: Action Dispatcher + Hikvision
**Status:** ✅ DONE
**Commit:** 2489aae
(Reused Hikvision ISAPI relay + Digest auth pattern from prior branch act.py, adapted into brief's structure.)

Checklist:
- [x] backend/actions/hikvision.py (Digest auth, ISAPI)
- [x] relay_set(port, state, duration) works — verified URL+body against stand-in
- [x] backend/actions/webhook.py (ntfy.sh, Discord, generic)
- [x] backend/actions/logger.py — JSONL append, thread-safe
- [x] backend/actions/dispatcher.py async coordinator — asyncio.to_thread, routes relay/webhook/log
- [x] scripts/test_hikvision_relay.py created
- [x] docs/HIKVISION_ISAPI.md cheatsheet
- [x] Tag v0.5-actions created
- [x] Commit + push done

**Notes:** 8/8 checks against a local stand-in HTTP server (no camera/cloud). Real Hikvision device not on hand; ISAPI URL/body/method verified exactly. Digest auth wired (HTTPDigestAuth).

### PAS 11: FastAPI Backend + Pipeline
**Status:** ✅ DONE
**Commit:** 287d4a6

Checklist:
- [x] backend/main.py with FastAPI app (lifespan starts/stops pipeline)
- [x] CORS configured
- [x] backend/core/pipeline.py main agent loop (perceive→reason→AFP→act, bg thread)
- [x] /conditions CRUD endpoints (+ /preview compile)
- [x] /events endpoints
- [x] /zones endpoints
- [x] /stream/live.mjpg with overlay — verified multipart + JPEG SOI bytes (real uvicorn)
- [x] /ws/events WebSocket
- [x] /ws/state WebSocket — verified delivers {running,fps,persons,conditions}
- [x] uvicorn starts, /docs accessible — 200
- [x] MJPEG stream visible in browser — snapshot 7748-byte JPEG + live multipart verified
- [x] Commit + push done

**Notes:** validated two ways — live uvicorn probes (REST/MJPEG/WS) + reproducible scripts/test_api.py TestClient **12/12**. Live loop ~13 FPS (det+pose+encode on CPU, single client). Added backend/config.py for centralized env.

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
- 2026-06-05 19:50 | PAS 3 | ✅ DONE — PersonDetector+TrackManager, webcam 31.9 FPS, bus.jpg 3 persons; committed 7e8103d
- 2026-06-05 20:00 | PAS 4 | ✅ DONE — PoseAnalyzer, skeleton verified, rules 9/9, 31.5 FPS; committed 672798a, tag v0.2-detection
- 2026-06-05 20:12 | PAS 5 | ✅ DONE — hybrid compiler 10/10 EN+RO; spotted & fixed an 8/10 regression by re-running; committed c97b346
- 2026-06-05 20:22 | PAS 6 | ✅ DONE — HybridEvaluator 11/11 checks (yolo/pose/vlm + adaptive sampling); committed bafac94, tag v0.3-agent-loop
- 2026-06-05 20:30 | PAS 7 | ✅ DONE — ReferenceFrame + AdaptiveSampler 5/5, empty→no VLM; committed cd84065
- 2026-06-05 20:40 | PAS 8 | ✅ DONE — AFP layer 4/4, 100 noisy→max 1/cooldown; committed 64529aa, tag v0.4-anti-false-positive
- 2026-06-05 20:48 | PAS 9 | ✅ DONE — SQLAlchemy Condition/Event/Zone, CRUD 6/6; committed b0a65bb
- 2026-06-05 21:00 | PAS 10 | ✅ DONE — action dispatcher (relay/webhook/log) 8/8 stand-in; committed 2489aae, tag v0.5-actions
- 2026-06-05 21:25 | PAS 11 | ✅ DONE — FastAPI backend + agent pipeline, live+TestClient 12/12; committed 287d4a6

## 🎓 Decision Log
- **VLM model:** moondream (primary, fast, 1.7GB) + llama3.2-vision (fallback for hard SEMANTIC, 7.8GB). Replaces brief's `llava:7b` suggestion — both already pulled locally. User-approved.
- **Python 3.13** instead of brief's 3.11 (machine has only 3.13/3.14). All ML wheels (torch 2.12, ultralytics 8.4.60, opencv 4.13) resolved cleanly. User-approved. Avoided 3.14 (wheel risk).
- **torch CPU-only** (cuda=False) — laptop has no configured CUDA. Plan: keep yolov8m; if PAS 3 FPS<15 on CPU, downgrade to yolov8n.
- **Prior branch not reused as base** — it was a cloud (Anthropic API) prototype. Kept on its own branch; we build the brief's local `backend/` architecture on `main`. Will borrow its Hikvision ISAPI (act.py) + debounce/cooldown patterns, adapted.
- **Ollama via HTTP** — app does not require `ollama` on PATH (uses localhost:11434). CLI checks use full exe path.
- **Repo layout** — cloned into `Desktop/Hack/hackaton-Watchful/`; work happens inside the repo.
- **Compiler is hybrid (deterministic-first), not pure-VLM** — moondream is unreliable as a *text* compiler (malformed JSON, hallucinated structural types for semantic inputs). Deterministic EN+RO rules handle all genuine structural patterns; unmatched → templated SEMANTIC. VLM-compile (llama3.2-vision via compile_heavy) only *rescues* structural types. This guarantees 100% compile success and correct routing, still 100% local. Diverges from brief's "compile via Moondream" but honors its intent (VLM routing + visual_question) more robustly.

## 💡 Ideas (out of scope)
- (nimic)

## ⚠️ Blockers
- (nimic)
