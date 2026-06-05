"""Hikvision ISAPI client — trigger camera I/O relay outputs via HTTP Digest auth.

ISAPI endpoint:
    PUT http://<ip>/ISAPI/System/IO/outputs/<port>/trigger
    body: <IOPortData><outputState>high|low</outputState></IOPortData>

``relay_set`` drives a relay high/low; with ``duration`` it schedules an auto-off.
"""
from __future__ import annotations

import os
import threading
from typing import Dict, Optional

import requests
from requests.auth import HTTPDigestAuth


def _env(key: str, default: str) -> str:
    v = os.environ.get(key)
    return v if v else default


class HikvisionClient:
    def __init__(
        self,
        ip: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        timeout: float = 5.0,
        scheme: str = "http",
    ) -> None:
        self.ip = ip if ip is not None else _env("HIKVISION_IP", "")
        self.user = user if user is not None else _env("HIKVISION_USER", "admin")
        self.password = password if password is not None else _env("HIKVISION_PASS", "")
        self.timeout = timeout
        self.scheme = scheme
        self.auth = HTTPDigestAuth(self.user, self.password)
        self._timers: Dict[int, threading.Timer] = {}

    @property
    def base(self) -> str:
        return f"{self.scheme}://{self.ip}"

    def _output_url(self, port: int) -> str:
        return f"{self.base}/ISAPI/System/IO/outputs/{port}/trigger"

    @staticmethod
    def _body(state) -> str:
        on = state in (True, 1, "high", "on", "ON", "High")
        s = "high" if on else "low"
        return (
            '<IOPortData version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">'
            f"<outputState>{s}</outputState></IOPortData>"
        )

    def relay_set(self, port: int = 1, state="high", duration: Optional[float] = None) -> bool:
        """Set output ``port`` high/low. With ``duration``, auto-revert after N seconds."""
        if not self.ip:
            raise RuntimeError("HIKVISION_IP not set")
        r = requests.put(self._output_url(port), data=self._body(state),
                         auth=self.auth, timeout=self.timeout)
        ok = r.status_code == 200
        if ok and duration:
            self._timers.pop(port, None)
            t = threading.Timer(duration, lambda: self._safe_set(port, "low"))
            t.daemon = True
            t.start()
            self._timers[port] = t
        return ok

    def pulse(self, port: int = 1, duration: float = 2.0) -> bool:
        """Turn a relay on, then off after ``duration`` seconds."""
        return self.relay_set(port, "high", duration)

    def _safe_set(self, port: int, state) -> None:
        try:
            requests.put(self._output_url(port), data=self._body(state),
                         auth=self.auth, timeout=self.timeout)
        except requests.RequestException:
            pass
