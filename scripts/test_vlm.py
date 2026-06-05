"""VLM smoke test: text-only health check, then capture one webcam frame and
ask Moondream a visual question. Prints the JSON answer + measured latency
(cold and warm).

Usage:  python scripts/test_vlm.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.video_source import VideoSource  # noqa: E402
from backend.vlm.client import OllamaVLMClient  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


def main() -> int:
    vlm = OllamaVLMClient()
    print(f"model={vlm.model}  heavy={vlm.heavy_model}  base={vlm.base_url}")

    # 1) connectivity health (tolerant of messy JSON)
    print(f"[health] server_reachable={vlm.health()}")

    # 2) capture a frame
    src = os.environ.get("VIDEO_SOURCE", "0")
    with VideoSource(src) as cam:
        for _ in range(5):
            cam.read()  # warmup
        frame = cam.read()
    if frame is None:
        print("ERROR: could not read a frame")
        return 2
    print(f"frame {frame.shape[1]}x{frame.shape[0]}")

    # 3) visual question, cold + warm latency
    q = "How many people are in this image?"
    hint = 'Schema: {"count": <int>, "confidence": <0.0-1.0>}'
    r = None
    for i in range(2):
        r = vlm.ask(frame, q, schema_hint=hint)
        print(f"[{'cold' if i == 0 else 'warm'}] latency={r.latency_ms}ms ok={r.ok} answer={r.answer}")

    ok = bool(r and r.ok)
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
