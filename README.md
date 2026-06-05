# 👁️ Watchful — Tell your camera what matters, in your own words

> **Hack A Ton 2026 · ThePlace Camera Agent (Track 2)**
> An AI agent that watches a live camera feed, understands natural-language
> conditions, and takes action — **100% local, zero cloud, zero cost.**

Security cameras see everything and understand nothing. Watchful lets you say
*"notify me when someone raises a hand in the jacuzzi"* or *"alert if someone
looks distressed"* — in plain language — and the agent perceives, reasons, and
acts. The hard part isn't detecting. It's **not firing on shadows.**

---

## 🔒 The promise: 100% local · 0 cost · 0 cloud

Everything runs on the laptop. No paid API key. Not a single byte to the cloud.

| Component | Local implementation | Cost |
|---|---|---|
| Vision-language model | **Ollama + Moondream** (fallback: `llama3.2-vision`) | 0 |
| Person detection | YOLOv8 (Ultralytics) | 0 |
| Pose estimation | YOLOv8-pose | 0 |
| Backend | FastAPI (localhost) | 0 |
| Frontend | React + Vite (localhost) | 0 |
| Database | SQLite file | 0 |
| Camera | RTSP (local Hikvision) or webcam | 0 |

For a premium venue with privacy concerns, *local isn't optional — it's the only
viable option.*

---

## 🧠 How it works

```
USER writes a condition in natural language
        │
        ▼
VLM COMPILER (Ollama, 1 text-only call)  →  structured PREDICATE
        │
        ▼
AGENT LOOP (continuous):
   PERCEIVE  →  frame + reference-frame diff
   REASON    →  router picks evaluator:  YOLO (count/zone) · Pose (geometry) · VLM (semantic)
   AFP       →  debounce · threshold · cooldown · zone mask · reference frame   ← the hard part
   ACT       →  Hikvision relay · webhook · log
```

A fast model (Moondream) handles compilation and routine checks; the heavier
`llama3.2-vision` is reserved for hard semantic conditions. YOLO/Pose run at high
FPS; the VLM is throttled (~1 FPS) and skipped entirely when the scene hasn't
changed.

---

## 🚀 Quickstart (local)

**Prerequisites:** [Ollama](https://ollama.com) running, Python 3.13, Node 18+.

```bash
# 1. Pull the local VLM (once)
ollama pull moondream
ollama pull llama3.2-vision   # optional, for hard semantic conditions

# 2. Backend
py -3.13 -m venv .venv
.\.venv\Scripts\activate          # Windows  (source .venv/bin/activate on *nix)
pip install -r requirements.txt
cp .env.example .env              # then edit VIDEO_SOURCE etc.
uvicorn backend.main:app --reload # → http://localhost:8000/docs

# 3. Frontend
cd frontend && npm install && npm run dev
```

---

## 📂 Structure

```
backend/
  core/        video source · detector · tracker · pose · reference frame · pipeline
  vlm/         Ollama client (OpenAI-compatible)
  predicates/  types · VLM compiler · hybrid evaluator
  antifalse/   debounce · cooldown · threshold
  actions/     dispatcher · hikvision · webhook · logger
  api/         conditions · events · zones · stream · ws
  models/      Condition · Event · Zone (SQLAlchemy)
frontend/      React + Vite + Tailwind
eval/          clips · ground_truth.json · run_eval.py
scripts/       test_camera · test_vlm · test_hikvision_relay
docs/          ARCHITECTURE · HIKVISION_ISAPI · PITCH_NOTES
```

---

## 📊 Progress

Build status lives in **[PROGRESS.md](PROGRESS.md)** — the persistent log of the
16-step autonomous build (PAS 0 → PAS 15).

---

*"Demo-ul care funcționează bate ambiția care nu." · "100% local. 0 cost."*
