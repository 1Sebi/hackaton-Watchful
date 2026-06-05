"""Temporal debounce — require N consecutive positive evaluations before firing.

Mechanism 2: the single biggest lever against firing on a one-frame fluke
(a shadow, a flicker, a momentary mis-detection). A negative resets the streak.
"""
from __future__ import annotations

from typing import Dict


class Debouncer:
    def __init__(self) -> None:
        self._streak: Dict[str, int] = {}

    def push(self, key: str, positive: bool, needed: int) -> bool:
        """Record one evaluation; return True once ``needed`` consecutive positives seen."""
        self._streak[key] = self._streak.get(key, 0) + 1 if positive else 0
        return self._streak.get(key, 0) >= max(1, needed)

    def streak(self, key: str) -> int:
        return self._streak.get(key, 0)

    def reset(self, key: str) -> None:
        self._streak[key] = 0
