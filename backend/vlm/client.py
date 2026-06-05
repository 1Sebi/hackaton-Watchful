"""Local VLM client over Ollama's OpenAI-compatible API.

Default model is a fast one (``moondream``) for compilation + routine checks;
pass ``heavy=True`` (or ``model=``) to escalate to a more capable model
(``llama3.2-vision``) for hard semantic conditions. Every call requests JSON
output and parses defensively, so a chatty model can't break the agent loop.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

import cv2
import numpy as np
from openai import APIConnectionError, APITimeoutError, OpenAI


def _env(key: str, default: str) -> str:
    v = os.environ.get(key)
    return v if v else default


@dataclass
class VLMResponse:
    answer: dict
    raw: str
    latency_ms: int
    model: str
    ok: bool = True

    def get(self, key: str, default: Any = None) -> Any:
        return self.answer.get(key, default)


class OllamaVLMClient:
    """Thin wrapper around the Ollama ``/v1`` endpoint via the OpenAI SDK."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        heavy_model: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        base = base_url or _env("OLLAMA_BASE_URL", "http://localhost:11434")
        if not base.rstrip("/").endswith("/v1"):
            base = base.rstrip("/") + "/v1"  # OpenAI SDK expects the /v1 suffix
        self.base_url = base
        self.model = model or _env("VLM_MODEL", "moondream")
        self.heavy_model = heavy_model or _env("VLM_MODEL_HEAVY", "llama3.2-vision")
        self.timeout = timeout
        self.client = OpenAI(base_url=self.base_url, api_key="ollama", timeout=timeout)

    # ── image encoding ───────────────────────────────────────────────────
    @staticmethod
    def encode_image(frame: np.ndarray, max_width: int = 768, quality: int = 85) -> str:
        """Downscale (<= max_width) + JPEG + base64 — smaller is faster, plenty for a VLM."""
        h, w = frame.shape[:2]
        if w > max_width:
            new_h = int(h * max_width / w)
            frame = cv2.resize(frame, (max_width, new_h))
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return base64.b64encode(buf).decode("utf-8")

    # ── defensive JSON parsing ───────────────────────────────────────────
    @staticmethod
    def _parse_json(raw: str) -> dict:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            m = re.search(r"\{.*\}", raw or "", re.DOTALL)  # first {...} block
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass
            return {"error": "parse_failed", "raw": raw}

    # ── main call ────────────────────────────────────────────────────────
    def ask(
        self,
        frame: Optional[np.ndarray],
        question: str,
        schema_hint: str = "",
        model: Optional[str] = None,
        heavy: bool = False,
        max_tokens: int = 256,
        retries: int = 1,
    ) -> VLMResponse:
        """Ask the VLM a question about ``frame`` (or text-only if ``frame is None``)."""
        use_model = model or (self.heavy_model if heavy else self.model)
        prompt = question
        prompt += f"\n\nReturn ONLY valid JSON. {schema_hint}".rstrip()

        content: list[dict[str, Any]] = []
        if frame is not None:
            b64 = self.encode_image(frame)
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            )
        content.append({"type": "text", "text": prompt})
        messages = [{"role": "user", "content": content}]

        start = time.time()
        last_err: Optional[Exception] = None
        for _attempt in range(retries + 1):
            try:
                resp = self.client.chat.completions.create(
                    model=use_model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0,
                    response_format={"type": "json_object"},
                )
                raw = resp.choices[0].message.content or ""
                latency = int((time.time() - start) * 1000)
                data = self._parse_json(raw)
                return VLMResponse(
                    answer=data, raw=raw, latency_ms=latency,
                    model=use_model, ok="error" not in data,
                )
            except (APIConnectionError, APITimeoutError) as e:
                last_err = e
                time.sleep(0.5)  # transient — retry
                continue
            except Exception as e:  # noqa: BLE001
                last_err = e
                break

        latency = int((time.time() - start) * 1000)
        return VLMResponse(
            answer={"error": "request_failed", "detail": str(last_err)},
            raw="", latency_ms=latency, model=use_model, ok=False,
        )

    def health(self) -> bool:
        """Cheap text-only round-trip to confirm the server is reachable.

        Tolerant of messy JSON — a parse failure still means the model replied;
        only a connection/timeout failure counts as unhealthy.
        """
        r = self.ask(None, 'Reply with JSON {"ok": true}', max_tokens=50)
        return r.answer.get("error") != "request_failed"
