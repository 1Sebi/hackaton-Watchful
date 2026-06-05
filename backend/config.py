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


settings = Settings()
