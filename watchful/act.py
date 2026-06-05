"""Act — the three action types the brief asks for:
  - relay   : trigger Hikvision I/O outputs via ISAPI (on/off/duration)
  - notify  : POST a webhook with alert details
  - log     : append a structured event to a JSONL file

All relay calls use HTTP Digest auth (Hikvision default).
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from requests.auth import HTTPDigestAuth

from .config import Action, CameraConfig


class Actuator:
    def __init__(
        self,
        camera: CameraConfig,
        webhook_url: str | None = None,
        log_path: str | Path = "events.jsonl",
        timeout: float = 5.0,
    ):
        self.camera = camera
        self.auth = HTTPDigestAuth(camera.user, camera.password)
        self.webhook_url = webhook_url
        self.log_path = Path(log_path)
        self.timeout = timeout
        self._timers: dict[int, threading.Timer] = {}

    # --- relays -----------------------------------------------------------
    def relay(self, port: int, on: bool = True) -> bool:
        """Set output `port` high (on) or low (off)."""
        state = "high" if on else "low"
        body = (
            f'<IOPortData version="2.0" '
            f'xmlns="http://www.hikvision.com/ver20/XMLSchema">'
            f"<outputState>{state}</outputState></IOPortData>"
        )
        url = f"{self.camera.isapi_base}/ISAPI/System/IO/outputs/{port}/trigger"
        try:
            r = requests.put(url, data=body, auth=self.auth, timeout=self.timeout)
            ok = r.status_code == 200
            self.log({"event": "relay", "port": port, "state": state, "ok": ok})
            return ok
        except requests.RequestException as e:
            self.log({"event": "relay_error", "port": port, "error": str(e)})
            return False

    def relay_pulse(self, port: int, duration_seconds: int) -> bool:
        """Turn a relay on, then schedule it off after `duration_seconds`."""
        ok = self.relay(port, on=True)
        # cancel any pending off for this port, then schedule a fresh one
        if port in self._timers:
            self._timers[port].cancel()
        t = threading.Timer(duration_seconds, self.relay, args=(port, False))
        t.daemon = True
        t.start()
        self._timers[port] = t
        return ok

    def list_outputs(self) -> str:
        """Discover which output ports exist on this device."""
        url = f"{self.camera.isapi_base}/ISAPI/System/IO/outputs"
        r = requests.get(url, auth=self.auth, timeout=self.timeout)
        return r.text

    # --- notify -----------------------------------------------------------
    def notify(self, message: str, extra: dict[str, Any] | None = None) -> bool:
        payload = {
            "message": message,
            "timestamp": _now(),
            **(extra or {}),
        }
        self.log({"event": "notify", **payload})
        if not self.webhook_url:
            return False
        try:
            r = requests.post(self.webhook_url, json=payload, timeout=self.timeout)
            return r.status_code < 400
        except requests.RequestException as e:
            self.log({"event": "notify_error", "error": str(e)})
            return False

    # --- log --------------------------------------------------------------
    def log(self, event: dict[str, Any]) -> None:
        event = {"ts": _now(), **event}
        with self.log_path.open("a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    # --- dispatch ---------------------------------------------------------
    def run_action(self, action: Action, context: dict[str, Any]) -> None:
        if action.type == "relay":
            if action.state == "on" and action.duration_seconds:
                self.relay_pulse(action.port, action.duration_seconds)
            else:
                self.relay(action.port, on=(action.state == "on"))
        elif action.type == "notify":
            msg = action.message or context.get("condition_id", "alert")
            self.notify(msg, extra={**action.extra, **context})
        elif action.type == "log":
            self.log({"event": "condition_met", "message": action.message, **context})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
