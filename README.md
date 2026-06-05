# 👁️ Watchful

> Tell a camera what to watch for in plain English; when it happens, the agent acts.

Hack A Ton 2026 · *Watchful* challenge (ThePlace). An AI agent that watches a live
**Hikvision IPCAM/NVR** feed and fires actions when **natural-language conditions** are met.

## How it works

```
            ┌─────────────┐   frame    ┌──────────────┐   verdict   ┌──────────────┐
  RTSP ───▶ │  PERCEIVE   │ ─────────▶ │  UNDERSTAND  │ ──────────▶ │    AGENT     │
            │ frames +    │  (only if  │ VLM checks   │ {met,conf}  │ debounce +   │
            │ motion gate │   motion)  │ the condition│             │ confidence + │
            └─────────────┘            └──────────────┘             │ cooldown     │
                                                                    └──────┬───────┘
                                                            fires ↓ when all pass
                                                   ┌──────────────────────────────┐
                                                   │ ACT: relay (ISAPI) / notify   │
                                                   │      (webhook) / log (JSONL)  │
                                                   └──────────────────────────────┘
```

- **Perceive** (`watchful/perceive.py`) — pulls frames over RTSP. A cheap frame-diff
  **motion gate** skips the VLM when nothing changed (big speed + cost win).
- **Understand** (`watchful/understand.py`) — a vision-language model turns each
  plain-English condition into a structured verdict `{met, confidence, reason}`.
- **Act** (`watchful/act.py`) — Hikvision **ISAPI** relays (on/off/duration),
  **webhook** notifications, and **JSONL** event logging.
- **Agent** (`watchful/agent.py`) — fires only when `met` **and** confidence ≥ min
  **and** N consecutive hits (**debounce**) **and** past **cooldown**. This is the
  anti-false-trigger layer the challenge is judged on.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in camera IP/creds + ANTHROPIC_API_KEY
```

## Run

```bash
# 1) sanity-check the camera: grab a frame + list relay outputs
python main.py --check

# 2) evaluate every condition once against a single frame
python main.py --once

# 3) run the agent against conditions.yaml
python main.py --poll 0.5

# 4) (stretch) natural-language UI to add/edit conditions + run live
streamlit run app.py
```

No camera handy? The brief allows a recorded-footage demo — point `CAM_CHANNEL`
at a test stream, or adapt `FrameSource` to read a local video file.

## Defining conditions

Edit `conditions.yaml` (or use the UI). Each condition is plain English plus the
reliability knobs:

```yaml
conditions:
  - id: jacuzzi-hand-raise
    prompt: A person in the jacuzzi raises a hand above their head.
    confidence_min: 0.75
    hits_needed: 3          # consecutive positive checks before firing
    cooldown_seconds: 60
    actions:
      - type: relay
        port: 1
        state: on
        duration_seconds: 300   # 5 minutes
```

Time-based conditions ("nobody for 15 minutes") are expressed as
`hits_needed ≈ seconds / poll_interval` — see the `empty-15min` example.

## Tuning false positives

| Lever | Where | Effect |
|---|---|---|
| `confidence_min` | per condition | reject weak detections |
| `hits_needed` | per condition | require sustained agreement (kills shadow flicker) |
| `cooldown_seconds` | per condition | stop repeat firing on the same event |
| motion gate `threshold` | `perceive.py` | ignore lighting flicker |
| `WATCHFUL_MODEL` | `.env` | bigger model = fewer mistakes, more latency |

## Tests

```bash
python -m pytest tests/ -q   # debounce / confidence / cooldown logic, no hardware
```

## Hikvision reference

- RTSP: `rtsp://USER:PASS@IP:554/Streaming/Channels/101` (main) or `/102` (substream)
- Relay trigger: `PUT /ISAPI/System/IO/outputs/{port}/trigger` (HTTP Digest auth)
- List outputs: `GET /ISAPI/System/IO/outputs`

## Project layout

```
watchful/
├── main.py              # CLI entrypoint
├── app.py               # Streamlit UI (stretch goal)
├── conditions.yaml      # natural-language conditions + actions
├── requirements.txt
├── .env.example
└── watchful/
    ├── config.py        # env + conditions loading
    ├── perceive.py      # RTSP frames + motion gate
    ├── understand.py    # VLM predicate evaluation
    ├── act.py           # ISAPI relays / webhook / logging
    └── agent.py         # debounce + confidence + cooldown loop
```

## Deliverables → this repo

- **Git repo + README + run instructions** — this file.
- **Demo** — `main.py` live on the provided camera, or recorded footage.
- **5-min pitch** — architecture (above), key decision (motion gate + debounce to
  trade a little latency for a low false-trigger rate), trade-offs (poll rate vs
  cost, model size vs accuracy).
