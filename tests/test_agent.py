"""Offline tests for the agent's firing logic — no camera or API needed.

  python -m pytest tests/ -q
"""
import time

from watchful.agent import Agent
from watchful.config import Action, Condition


class FakeSource:
    def __init__(self, frames):
        self.frames = list(frames)
    def open(self): pass
    def close(self): pass
    def read(self):
        return self.frames.pop(0) if self.frames else None
    def motion_changed(self, frame, threshold=1.5):
        return True


class FakeVLM:
    def __init__(self, verdicts):
        self.verdicts = list(verdicts)
    def check(self, frame, prompt):
        return self.verdicts.pop(0)


class FakeActuator:
    def __init__(self):
        self.fired = []
    def run_action(self, action, context):
        self.fired.append((action.type, context["condition_id"]))


def make_condition(hits=3, cooldown=0):
    return Condition(
        id="c1", prompt="x", confidence_min=0.7,
        hits_needed=hits, cooldown_seconds=cooldown,
        actions=[Action(type="log", message="hit")],
    )


def test_debounce_requires_consecutive_hits():
    cond = make_condition(hits=3)
    verdicts = [
        {"met": True, "confidence": 0.9, "reason": ""},   # streak 1
        {"met": True, "confidence": 0.9, "reason": ""},   # streak 2
        {"met": True, "confidence": 0.9, "reason": ""},   # streak 3 -> fire
    ]
    act = FakeActuator()
    a = Agent(FakeSource([1, 2, 3]), [cond], act, FakeVLM(verdicts))
    for _ in range(3):
        a.step()
    assert act.fired == [("log", "c1")]


def test_low_confidence_breaks_streak():
    cond = make_condition(hits=2)
    verdicts = [
        {"met": True, "confidence": 0.9, "reason": ""},   # streak 1
        {"met": True, "confidence": 0.4, "reason": ""},   # below min -> reset
        {"met": True, "confidence": 0.9, "reason": ""},   # streak 1 again
    ]
    act = FakeActuator()
    a = Agent(FakeSource([1, 2, 3]), [cond], act, FakeVLM(verdicts))
    for _ in range(3):
        a.step()
    assert act.fired == []   # never reached 2-in-a-row


def test_cooldown_blocks_refire():
    cond = make_condition(hits=1, cooldown=999)
    verdicts = [
        {"met": True, "confidence": 0.9, "reason": ""},   # fire
        {"met": True, "confidence": 0.9, "reason": ""},   # blocked by cooldown
    ]
    act = FakeActuator()
    a = Agent(FakeSource([1, 2]), [cond], act, FakeVLM(verdicts))
    a.step()
    a.step()
    assert act.fired == [("log", "c1")]   # only once
