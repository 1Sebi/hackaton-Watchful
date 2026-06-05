"""Understand — a vision-language model evaluates a natural-language condition
against a single frame and returns a structured verdict.

We force JSON output so the agent loop can decide programmatically. Default
model is a fast one (good for polling); bump to a larger model for tricky
conditions via the WATCHFUL_MODEL env var.
"""
from __future__ import annotations

import base64
import json
import os
import re

import cv2
import numpy as np

try:
    from anthropic import Anthropic
except ImportError:  # keep import-time failure friendly
    Anthropic = None  # type: ignore

DEFAULT_MODEL = os.environ.get("WATCHFUL_MODEL", "claude-sonnet-4-6")

SYSTEM = (
    "You are a precise visual condition checker for a security/venue camera. "
    "You are shown ONE frame and ONE condition. Decide ONLY whether the condition "
    "is literally true in THIS frame. Do not speculate about the past or future. "
    "Be conservative: if you are not sure, set met=false. Shadows, reflections, "
    "posters, and screens are NOT people. "
    'Reply with ONLY a JSON object, no prose: '
    '{"met": <true|false>, "confidence": <0.0-1.0>, "reason": "<short>"}'
)


def encode_frame(frame: np.ndarray, max_width: int = 768, quality: int = 80) -> str:
    """Downscale + JPEG-encode + base64. Smaller frame = faster, cheaper, plenty for VLM."""
    h, w = frame.shape[:2]
    if w > max_width:
        scale = max_width / w
        frame = cv2.resize(frame, (max_width, int(h * scale)))
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(buf).decode()


class VLM:
    def __init__(self, model: str = DEFAULT_MODEL):
        if Anthropic is None:
            raise RuntimeError("anthropic package not installed. `pip install anthropic`")
        self.client = Anthropic()  # reads ANTHROPIC_API_KEY from env
        self.model = model

    def check(self, frame: np.ndarray, condition_prompt: str) -> dict:
        """Return {'met': bool, 'confidence': float, 'reason': str}."""
        b64 = encode_frame(frame)
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=200,
            system=SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": f'Condition: "{condition_prompt}"'},
                    ],
                }
            ],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return self._parse(text)

    @staticmethod
    def _parse(text: str) -> dict:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        try:
            data = json.loads(m.group(0) if m else text)
            return {
                "met": bool(data.get("met", False)),
                "confidence": float(data.get("confidence", 0.0)),
                "reason": str(data.get("reason", "")),
            }
        except Exception:
            return {"met": False, "confidence": 0.0, "reason": f"unparseable: {text[:80]}"}
