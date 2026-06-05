"""Agent — the control loop.

For each frame that passes the motion gate, evaluate every enabled condition
with the VLM. Fire a condition's actions only when ALL of these hold:
  - met == true
  - confidence >= condition.confidence_min
  - we've now seen `hits_needed` positive checks in a row  (debounce)
  - at least `cooldown_seconds` have passed since the last fire  (anti-spam)

This is the part that scores the "low false-trigger rate" points.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .act import Actuator
from .config import Condition
from .perceive import FrameSource
from .understand import VLM


@dataclass
class _State:
    streak: int = 0
    last_fire: float = 0.0


class Agent:
    def __init__(
        self,
        source: FrameSource,
        conditions: list[Condition],
        actuator: Actuator,
        vlm: VLM,
        poll_interval: float = 0.5,
        use_motion_gate: bool = True,
        on_event=None,  # optional callback(dict) for UI/streaming
    ):
        self.source = source
        self.conditions = conditions
        self.actuator = actuator
        self.vlm = vlm
        self.poll_interval = poll_interval
        self.use_motion_gate = use_motion_gate
        self.on_event = on_event
        self._state: dict[str, _State] = {c.id: _State() for c in conditions}
        self._running = False

    def _emit(self, payload: dict) -> None:
        if self.on_event:
            try:
                self.on_event(payload)
            except Exception:
                pass

    def step(self) -> None:
        frame = self.source.read()
        if frame is None:
            return
        if self.use_motion_gate and not self.source.motion_changed(frame):
            return

        for cond in self.conditions:
            if not cond.enabled:
                continue
            st = self._state[cond.id]
            verdict = self.vlm.check(frame, cond.prompt)
            positive = verdict["met"] and verdict["confidence"] >= cond.confidence_min
            st.streak = st.streak + 1 if positive else 0

            self._emit({"condition": cond.id, "verdict": verdict, "streak": st.streak})

            ready = st.streak >= cond.hits_needed
            cooled = (time.time() - st.last_fire) >= cond.cooldown_seconds
            if ready and cooled:
                self._fire(cond, verdict)
                st.streak = 0
                st.last_fire = time.time()

    def _fire(self, cond: Condition, verdict: dict) -> None:
        context = {
            "condition_id": cond.id,
            "prompt": cond.prompt,
            "confidence": verdict["confidence"],
            "reason": verdict["reason"],
        }
        for action in cond.actions:
            self.actuator.run_action(action, context)
        self._emit({"fired": cond.id, **context})

    def run(self) -> None:
        self._running = True
        self.source.open()
        print(f"[watchful] watching {len(self.conditions)} condition(s). Ctrl-C to stop.")
        try:
            while self._running:
                t0 = time.time()
                self.step()
                dt = time.time() - t0
                time.sleep(max(0.0, self.poll_interval - dt))
        except KeyboardInterrupt:
            print("\n[watchful] stopping.")
        finally:
            self.source.close()

    def stop(self) -> None:
        self._running = False
