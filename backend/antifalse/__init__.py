"""Anti-false-positive layer — "the hard part": don't fire on shadows.

Five mechanisms protect every trigger:
  1. threshold     — confidence must clear the predicate's min_confidence   (threshold.py)
  2. debounce      — N consecutive positives required                       (debouncer.py)
  3. cooldown      — mute re-fires for cooldown_seconds                      (cooldown.py)
  4. zone mask     — only count detections inside the predicate's polygon    (evaluator.py)
  5. reference frame — skip evaluation when the scene hasn't changed         (reference_frame.py)

``AntiFalsePositive.should_fire`` chains mechanisms 1-3 (4 & 5 act upstream in
perception/evaluation) and returns (fire, reason).
"""
from __future__ import annotations

import time
from typing import Optional, Tuple

from backend.antifalse.cooldown import Cooldown
from backend.antifalse.debouncer import Debouncer
from backend.antifalse.threshold import ThresholdGate

__all__ = ["ThresholdGate", "Debouncer", "Cooldown", "AntiFalsePositive", "predicate_key"]


def predicate_key(predicate) -> str:
    return f"{predicate.type}|{predicate.original_text}|{predicate.visual_question}"


class AntiFalsePositive:
    def __init__(self) -> None:
        self.threshold = ThresholdGate()
        self.debouncer = Debouncer()
        self.cooldown = Cooldown()

    def should_fire(self, predicate, result, now: Optional[float] = None) -> Tuple[bool, str]:
        """Decide whether ``result`` for ``predicate`` should trigger an action."""
        now = time.time() if now is None else now
        key = predicate_key(predicate)

        # 1) threshold — weak/negative breaks the streak
        if not self.threshold.passes(result, predicate):
            self.debouncer.reset(key)
            return False, "below_threshold"

        # 2) debounce — need N consecutive positives
        if not self.debouncer.push(key, True, predicate.min_consecutive):
            return False, f"debounce {self.debouncer.streak(key)}/{predicate.min_consecutive}"

        # 3) cooldown — mute right after a fire
        if not self.cooldown.allow(key, predicate.cooldown_seconds, now):
            return False, "cooldown"

        self.cooldown.trigger(key, now)
        self.debouncer.reset(key)  # require a fresh streak before re-firing
        return True, "fired"
