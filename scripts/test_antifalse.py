"""Anti-false-positive layer test.

  - threshold: low-confidence positives never fire
  - debounce: 2-on-1-off pattern never reaches N consecutive -> never fires
  - cooldown: 100 noisy evals -> consecutive fires are >= cooldown apart
              (i.e. at most one trigger per cooldown window)
  - happy path: 3 strong consecutive -> fires once, then cooldown mutes

Usage:  python scripts/test_antifalse.py
"""
from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.antifalse import AntiFalsePositive  # noqa: E402
from backend.predicates.types import Predicate, PredicateType  # noqa: E402


class R:
    def __init__(self, detected: bool, confidence: float):
        self.detected = detected
        self.confidence = confidence


def _pred(text: str) -> Predicate:
    return Predicate(type=PredicateType.COUNT_GT, params={"value": 0},
                     min_confidence=0.7, min_consecutive=3, cooldown_seconds=30,
                     original_text=text)


def main() -> int:
    checks = {}

    # 1) threshold: 50 strong-but-low-confidence positives -> never fires
    afp = AntiFalsePositive()
    p = _pred("low conf")
    fires = sum(afp.should_fire(p, R(True, 0.5), now=float(t))[0] for t in range(50))
    checks["threshold_blocks_lowconf"] = fires == 0

    # 2) debounce: pattern on,on,off,... never 3 in a row -> never fires
    afp = AntiFalsePositive()
    p = _pred("debounce")
    seq = [True, True, False] * 20
    fires = sum(afp.should_fire(p, R(p_ok, 0.9), now=float(t))[0] for t, p_ok in enumerate(seq))
    checks["debounce_needs_consecutive"] = fires == 0

    # 3) 100 noisy evals -> fires respect the cooldown
    random.seed(42)
    afp = AntiFalsePositive()
    p = _pred("noisy")
    fire_times = []
    for t in range(100):
        if random.random() < 0.25:           # 25% noise: a miss / weak frame
            res = R(False, 0.0) if random.random() < 0.5 else R(True, 0.4)
        else:
            res = R(True, 0.85 + random.random() * 0.1)
        fired, _ = afp.should_fire(p, res, now=float(t))
        if fired:
            fire_times.append(t)
    gaps = [b - a for a, b in zip(fire_times, fire_times[1:])]
    min_gap = min(gaps) if gaps else 999
    print(f"[3] noisy fires at {fire_times} (gaps {gaps}, min_gap={min_gap})")
    checks["cooldown_min_gap"] = (len(fire_times) >= 1) and (min_gap >= 30) and (len(fire_times) <= 4)

    # 4) happy path: 3 strong consecutive -> exactly one fire, then muted
    afp = AntiFalsePositive()
    p = _pred("happy")
    res_seq = [afp.should_fire(p, R(True, 0.95), now=float(t))[0] for t in range(5)]
    print(f"[4] first-5-strong fires: {res_seq}")
    checks["happy_one_fire"] = res_seq == [False, False, True, False, False]

    passed = 0
    for k, v in checks.items():
        print(f"   [{'OK' if v else 'XX'}] {k}")
        passed += bool(v)
    print(f"RESULT: {passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
