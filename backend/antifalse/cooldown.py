"""Per-key cooldown — suppress re-fires for N seconds after a trigger.

Mechanism 3: even a genuinely true condition shouldn't spam actions. After a
fire, the same predicate is muted for ``cooldown_seconds`` (anti-spam).
"""
from __future__ import annotations

import time
from typing import Dict, Optional


class Cooldown:
    def __init__(self) -> None:
        self._last_fire: Dict[str, float] = {}

    def allow(self, key: str, seconds: float, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        last = self._last_fire.get(key)
        return last is None or (now - last) >= seconds

    def trigger(self, key: str, now: Optional[float] = None) -> None:
        self._last_fire[key] = time.time() if now is None else now

    def remaining(self, key: str, seconds: float, now: Optional[float] = None) -> float:
        now = time.time() if now is None else now
        last = self._last_fire.get(key)
        if last is None:
            return 0.0
        return max(0.0, seconds - (now - last))
