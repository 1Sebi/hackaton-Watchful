# Watchful — 5-minute pitch

> One-liner: **"Tell your camera what matters, in your own words — and it acts. 100% local, zero cloud, zero cost."**

## Timing (5:00)

### 0:00–0:30 — Hook
- "40 cameras, 1 guard. Cameras see everything and understand nothing."
- "Watchful changes that: you tell the camera what matters — in your own words — and it acts."
- "And it runs **entirely on this laptop**. No cloud, no API bill, no data leaving the building."

### 0:30–1:30 — LIVE Demo #1 (deterministic, reliable)
- In the UI, type: **"someone raises their hand"** → show the **compiled predicate** preview (POSE_HAND_RAISED → pose evaluator) appear instantly.
- Click **Add**. A volunteer raises a hand → bbox turns, **"#id … HAND^"** label, event pops in the live **Event log** → action fires (relay click / webhook / log line).
- Point: "Natural language → a checkable predicate → an action. No training, no config files."

### 1:30–2:30 — LIVE Demo #2 (semantic, the wow)
- Type: **"more than 3 people"** AND **"no one for 10 seconds"** (two rules at once).
- Crowd in → count rule fires. Everyone steps out → after 10s the absence rule fires.
- Mention semantic: **"someone looks distressed"** routes to the local VLM (llama3.2-vision) on a crop — abstract conditions, still 100% local.

### 2:30–3:30 — The hard part: NOT firing on shadows
- Brief says it plainly: *"Not detecting. Not firing on shadows."*
- We measured it. **Eval: 30 cases (10 true / 10 trap / 10 neutral).**
  - **Precision 100% · False-trigger rate 0.0% · Recall 90% · F1 94.7%.**
  - **Trap 10/10, Neutral 10/10 — zero false positives.**
- Five anti-false-positive mechanisms: confidence threshold, N-consecutive debounce, cooldown, zone mask, reference-frame gating.
- "100 noisy evaluations → at most one trigger per cooldown window."

### 3:30–4:30 — Architecture & trade-offs
- Agentic, exactly per the brief: **VLM compiles NL → predicate; an agent loop perceives → reasons → acts.**
- **Hybrid routing:** YOLOv8 for counts/zones, YOLOv8-pose for postures (fast, deterministic, ~30 FPS), local VLM only for the genuinely semantic cases (adaptively sampled at ~1 FPS, skipped on a static scene).
- "Everyone else calls a cloud LLM. We run **Ollama + Moondream / llama3.2-vision locally**. For a premium venue with a jacuzzi, privacy isn't a nice-to-have — local is the only viable option. No internet, no monthly bill."

### 4:30–5:00 — Vision & ask
- Roadmap: multi-camera, on-device fine-tuning from operator feedback, Hikvision relay actions on real I/O.
- "ThePlace can run this on-site, offline, today. Who wants to see it installed next week?"

## Demo safety net
- **Backup video** (`scripts/record_demo.py` records the annotated live feed) in case the volunteer demo slips.
- If a relay isn't handy: the **webhook** (ntfy.sh) and **log** actions show the same trigger — same dispatcher path.
- Wi-Fi dies? Everything is localhost — unaffected.

## Numbers to have on the tongue
- Precision **100%**, false-trigger rate **0.0%**, recall 90%, F1 94.7% (30-case eval).
- Detection ~**30 FPS** (YOLOv8n, CPU), live agent loop ~**13 FPS** with overlays.
- VLM warm latency ~**250 ms** (moondream); compile is instant for common rules (deterministic).
- Cost: **€0**. Cloud calls: **0**.

## Judging rubric hooks (Track 2)
- Working demo 25% → two live demos + backup video.
- Problem & impact 20% → 40-cams/1-guard, privacy, zero cost.
- Solution & innovation 20% → agentic hybrid, 100% local.
- Tech & architecture 15% → VLM-compiler + hybrid evaluator + 5-mechanism AFP.
- Pitch 10% → this script, rehearsed.
- Post-event feasibility 10% → runs offline on a laptop, Hikvision-ready.
