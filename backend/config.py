"""Central configuration — reads .env once and exposes typed settings."""
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


def _f(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


class Settings:
    VIDEO_SOURCE: str = os.environ.get("VIDEO_SOURCE", "0")
    OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    VLM_MODEL: str = os.environ.get("VLM_MODEL", "moondream")
    VLM_MODEL_HEAVY: str = os.environ.get("VLM_MODEL_HEAVY", "llama3.2-vision")
    DETECTION_MODEL: str = os.environ.get("DETECTION_MODEL", "yolov8m.pt")
    POSE_MODEL: str = os.environ.get("POSE_MODEL", "yolov8n-pose.pt")
    DETECTION_CONFIDENCE: float = _f("DETECTION_CONFIDENCE", 0.25)
    # YOLO inference size (multiple of 32). 640 = sweet spot on CPU; bigger
    # helps small/distant people at 2-3x cost.
    DETECTION_IMGSZ: int = int(_f("DETECTION_IMGSZ", 640))
    # Resize each captured frame to this width before detection/draw/encode.
    # The single sub-stream (after upgrade_substreams.py) is already ~720p, so
    # leaving FRAME_MAX_WIDTH=1280 is effectively a no-op — kept as a safety
    # net for cameras whose sub profile someone bumped above 1280.
    FRAME_MAX_WIDTH: int = int(_f("FRAME_MAX_WIDTH", 1280))
    VLM_MAX_FPS: float = _f("VLM_MAX_FPS", 1.0)
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "sqlite:///watchful.db")
    # ntfy.sh phone notifications. A condition with action {"type":"ntfy"} posts to
    # NTFY_BASE_URL/NTFY_TOPIC. Public service -> generic alert text only.
    NTFY_BASE_URL: str = os.environ.get("NTFY_BASE_URL", "https://ntfy.sh")
    NTFY_TOPIC: str = os.environ.get("NTFY_TOPIC", "")
    # ── Telegram bot (action {"type":"telegram"}) ──
    TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.environ.get("TELEGRAM_CHAT_ID", "")
    # ── WhatsApp via CallMeBot (action {"type":"whatsapp"}) ──
    WHATSAPP_PHONE: str = os.environ.get("WHATSAPP_PHONE", "")
    WHATSAPP_APIKEY: str = os.environ.get("WHATSAPP_APIKEY", "")
    # Motion gate: % of pixels that must change frame-to-frame to consider the
    # scene "moving" (used by the tile motion dot and VLM gating).
    MOTION_MIN_PCT: float = _f("MOTION_MIN_PCT", 0.6)
    # Cap rate at which a NON-visible rule camera runs YOLO. Visible cameras
    # run as fast as decode + lock-serialized YOLO allow; non-visible rule cams
    # are throttled so they don't steal CPU from what the user is watching.
    MONITOR_FPS: float = _f("MONITOR_FPS", 1.5)


settings = Settings()


# ── Camera registry (multi-camera grid) ──────────────────────────────────
# cameras.json carries id/name/nvr/channel (NO secrets, committed); the RTSP URL
# is assembled here from the NVR ip+password in .env so credentials never touch git.
import json as _json  # noqa: E402
from pathlib import Path as _Path  # noqa: E402
from urllib.parse import quote as _quote  # noqa: E402


def _nvr_creds(tag: str):
    ip = os.environ.get(f"{tag}_IP", "")
    user = os.environ.get(f"{tag}_USER", "admin")
    pw = os.environ.get(f"{tag}_PASS", "")
    return ip, user, pw


def _build_rtsp(ip: str, user: str, pw: str, channel: int) -> str:
    return f"rtsp://{user}:{_quote(pw, safe='')}@{ip}:554/Streaming/Channels/{channel}"


def _load_cameras():
    """Resolve backend/cameras.json into [{id,name,room,url}] using .env NVR creds.

    ONE stream per camera: the sub-stream (channel x02). Reconfigure that sub
    profile via scripts/upgrade_substreams.py to whatever quality detection
    needs. Cameras whose NVR creds aren't in .env are skipped; ENABLED_ROOMS
    in .env optionally restricts to a subset of rooms.
    """
    path = _Path(__file__).resolve().parent / "cameras.json"
    cams, default = [], None
    _enabled = {r.strip() for r in os.environ.get("ENABLED_ROOMS", "").split(",") if r.strip()}
    try:
        spec = _json.loads(path.read_text(encoding="utf-8"))
        default = spec.get("default_active")
        for c in spec.get("cameras", []):
            if _enabled and c.get("room") not in _enabled:
                continue
            ip, user, pw = _nvr_creds(str(c.get("nvr", "")))
            if not ip or not pw:
                continue
            sub_ch = int(c["channel"])  # x02 sub-stream — the single source
            cams.append({
                "id": c["id"],
                "name": c.get("name", c["id"]),
                "room": c.get("room", c.get("name", c["id"])),
                "url": _build_rtsp(ip, user, pw, sub_ch),
            })
    except Exception:
        cams = []
    if not cams:  # backward-compatible single-camera mode (no NVR creds)
        cams = [{"id": "camera", "name": "Camera", "room": "Camera",
                 "url": settings.VIDEO_SOURCE}]
        default = "camera"
    if default not in {c["id"] for c in cams}:
        default = cams[0]["id"]
    return cams, default


settings.CAMERAS, settings.DEFAULT_ACTIVE = _load_cameras()
