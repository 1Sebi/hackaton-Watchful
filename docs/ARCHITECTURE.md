# Watchful — Architecture

Watchful turns a natural-language condition into a checkable predicate and runs an
agent loop that perceives, reasons, and acts — **entirely locally**.

```
USER: "someone raises their hand in the jacuzzi"
   │
   ▼
┌──────────────────────────────────────────────────────────────┐
│ COMPILER (backend/predicates/compiler.py)                    │
│  deterministic EN+RO rules  ──▶ structural predicate         │
│  (counts / postures / zones / absence)                       │
│  else ──▶ local VLM (text)  ──▶ SEMANTIC predicate           │
└──────────────────────────────────────────────────────────────┘
   │  Predicate{type, evaluator, params, visual_question, thresholds}
   ▼  (stored in SQLite)
┌──────────────────────────────────────────────────────────────┐
│ AGENT LOOP (backend/core/pipeline.py, background thread)     │
│                                                              │
│  PERCEIVE  VideoSource ─▶ frame                              │
│            ReferenceFrame: significant change? (skip VLM)    │
│                                                              │
│  REASON    YOLOv8 detect+track  (≈30 FPS, every frame)       │
│            YOLOv8-pose          (postures)                   │
│            HybridEvaluator routes per predicate.evaluator:   │
│              yolo  → count / zone / absence                  │
│              pose  → hand raised / sitting / standing        │
│              vlm   → semantic crop → Ollama (≤1 FPS, cached) │
│                                                              │
│  AFP       threshold → debounce(N) → cooldown                │
│            (+ zone mask, reference frame)   "the hard part"  │
│                                                              │
│  ACT       ActionDispatcher → Hikvision relay / webhook / log│
└──────────────────────────────────────────────────────────────┘
   │
   ▼  annotated MJPEG + WebSocket events/state  ─▶  React UI
```

## Components

| Layer | Module | Role |
|---|---|---|
| Capture | `core/video_source.py` | webcam / RTSP / file, buffer-1, reconnect (MSMF on Windows = 30 FPS) |
| Detect | `core/detector.py` | YOLOv8n person detection + ByteTrack ids |
| Track | `core/tracker.py` | per-id duration, positions, prune, active count |
| Pose | `core/pose_analyzer.py` | COCO-17 keypoints, hand-raised/sitting/standing, IoU association |
| VLM | `vlm/client.py` | Ollama OpenAI-compat (moondream fast / llama3.2-vision heavy), JSON mode |
| Compile | `predicates/compiler.py` | NL → Predicate (hybrid: rules + VLM fallback) |
| Evaluate | `predicates/evaluator.py` | route to yolo/pose/vlm, adaptive VLM sampling |
| Reference | `core/reference_frame.py` | skip VLM when the scene is static |
| AFP | `antifalse/` | threshold · debounce · cooldown (+ zone mask, reference frame) |
| Store | `database.py`, `models/` | SQLite: Condition / Event / Zone |
| Actions | `actions/` | Hikvision ISAPI relay, webhook (ntfy/Discord), JSONL logger, async dispatcher |
| API | `api/`, `main.py` | REST CRUD, MJPEG, WebSockets |
| Visualize | `visualizer.py` | zones, trails, skeletons, labeled bboxes, HUD |
| UI | `frontend/` | React + Vite + Tailwind dashboard |

## Why hybrid (not pure-VLM)
Counts, zones, and postures are deterministic and fast — YOLO/pose answer them at
~30 FPS with no hallucination. The VLM is reserved for genuinely abstract
conditions ("looks distressed", "unattended bag"), throttled to ~1 FPS and skipped
when nothing changed. This is what keeps it **cost-zero and reliable**.

## The hard part (low false-trigger rate)
Five mechanisms gate every action; measured **precision 100% / false-trigger rate
0.0%** on a 30-case eval (see `eval/results.md`). A single shadow or one-frame
flicker never fires — debounce needs N consecutive positives, cooldown mutes
re-fires, and the reference frame suppresses evaluation on a static scene.

## 100% local
Ollama runs the VLM on-device; YOLO/pose are local PyTorch; storage is a SQLite
file; the UI is localhost. No external API, no key, no internet dependency.
