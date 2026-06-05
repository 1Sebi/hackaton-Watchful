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
    DETECTION_MODEL: str = os.environ.get("DETECTION_MODEL", "yolov8n.pt")
    POSE_MODEL: str = os.environ.get("POSE_MODEL", "yolov8n-pose.pt")
    DETECTION_CONFIDENCE: float = _f("DETECTION_CONFIDENCE", 0.5)
    # YOLO inference size (multiple of 32). Bigger recovers small/distant people
    # on wide overhead shots at the cost of CPU. 640 = default, 960 = recommended.
    DETECTION_IMGSZ: int = int(_f("DETECTION_IMGSZ", 960))
    # Resize each captured frame to this width before detection/draw/encode.
    # Lets you capture a sharp high-res stream (even 4K main) while keeping YOLO
    # fast on CPU. 0 = no resize (use the native stream resolution).
    FRAME_MAX_WIDTH: int = int(_f("FRAME_MAX_WIDTH", 0))
    VLM_MAX_FPS: float = _f("VLM_MAX_FPS", 1.0)
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "sqlite:///watchful.db")
    # ntfy.sh phone notifications. A condition with action {"type":"ntfy"} posts to
    # NTFY_BASE_URL/NTFY_TOPIC. Public service -> generic alert text only.
    NTFY_BASE_URL: str = os.environ.get("NTFY_BASE_URL", "https://ntfy.sh")
    NTFY_TOPIC: str = os.environ.get("NTFY_TOPIC", "")
    # ── Multi-camera grid ──
    # % of pixels that must change frame-to-frame for the OpenCV motion gate to
    # consider the scene "moving" and run YOLO (lower = more sensitive).
    MOTION_MIN_PCT: float = _f("MOTION_MIN_PCT", 0.6)
    # Display refresh of the ACTIVE camera (decoupled from detection -> smooth).
    RENDER_FPS: float = _f("RENDER_FPS", 20.0)
    # Display refresh of the inactive grid tiles (cheap; lower saves CPU).
    GRID_TILE_FPS: float = _f("GRID_TILE_FPS", 6.0)
    # Cap how often the active camera actually runs YOLO. 1 = analyze one frame
    # per second (plenty for an emergency monitor; makes a sharp 4K feed affordable).
    DETECT_MAX_FPS: float = _f("DETECT_MAX_FPS", 1.0)
    # Inactive cameras refresh their tile people-count this often (seconds). They
    # only count when the shared model lock is free, so they never slow the active
    # camera. 0 disables per-tile counting. ~8s keeps every tile live cheaply.
    GRID_COUNT_INTERVAL: float = _f("GRID_COUNT_INTERVAL", 8.0)


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
    # URL-encode the password (@ -> %40, $ -> %24, ...) so RTSP parsing is safe.
    return f"rtsp://{user}:{_quote(pw, safe='')}@{ip}:554/Streaming/Channels/{channel}"


def _load_cameras():
    """Resolve backend/cameras.json into [{id,name,url}] using .env NVR creds.

    Cameras whose NVR creds are absent are skipped. Falls back to a single
    camera wrapping VIDEO_SOURCE when no registry/creds are available.
    """
    path = _Path(__file__).resolve().parent / "cameras.json"
    cams, default = [], None
    try:
        spec = _json.loads(path.read_text(encoding="utf-8"))
        default = spec.get("default_active")
        for c in spec.get("cameras", []):
            ip, user, pw = _nvr_creds(str(c.get("nvr", "")))
            if not ip or not pw:
                continue  # NVR creds not in .env -> skip this camera
            sub_ch = int(c["channel"])                 # x02 sub-stream (light, for tiles)
            main_ch = (sub_ch // 100) * 100 + 1         # x01 main stream (4K, for active)
            cams.append({
                "id": c["id"],
                "name": c.get("name", c["id"]),
                "url": _build_rtsp(ip, user, pw, sub_ch),        # tile / inactive
                "main_url": _build_rtsp(ip, user, pw, main_ch),  # 4K when AI-active
            })
    except Exception:
        cams = []
    if not cams:  # backward-compatible single-camera mode
        cams = [{"id": "camera", "name": "Camera",
                 "url": settings.VIDEO_SOURCE, "main_url": settings.VIDEO_SOURCE}]
        default = "camera"
    if default not in {c["id"] for c in cams}:
        default = cams[0]["id"]
    return cams, default


settings.CAMERAS, settings.DEFAULT_ACTIVE = _load_cameras()
