"""ReferenceFrame + AdaptiveSampler test (deterministic, synthetic frames).

  - static empty scene -> after warmup, no significant change -> VLM skipped
  - a real change (someone appears) -> significant change -> VLM runs
  - stable scene past update_interval -> reference auto-refreshes
  - forced interval -> VLM runs even on a static scene

Usage:  python scripts/test_reference.py
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.reference_frame import AdaptiveSampler, ReferenceFrame  # noqa: E402


def main() -> int:
    empty = np.full((480, 640, 3), 50, dtype=np.uint8)
    noisy = empty.copy()
    noisy[::7, ::7] = 54  # tiny sub-threshold noise
    changed = empty.copy()
    changed[120:360, 240:420] = 230  # a big bright blob = "someone appeared"

    checks = {}

    # 1) static scene -> VLM runs once (warmup), then skipped
    samp = AdaptiveSampler(ReferenceFrame(), force_interval=1e9)
    runs = [samp.should_run_vlm(empty if i % 2 == 0 else noisy, now=float(i)) for i in range(10)]
    print(f"[1] static runs over 10 frames: {runs}")
    checks["static_skips_vlm"] = runs[0] is True and not any(runs[1:])

    # 2) a real change -> VLM runs
    checks["change_runs_vlm"] = samp.should_run_vlm(changed, now=100.0) is True

    # 3) back to empty (matches reference) -> skipped again
    checks["return_to_static_skips"] = samp.should_run_vlm(empty, now=101.0) is False

    # 4) auto-update of reference after update_interval on a stable scene
    ref = ReferenceFrame(update_interval=5.0)
    ref.significant_change(empty, now=0.0)        # init (last_update=0)
    ref.significant_change(empty, now=10.0)       # stable & >5s -> refresh
    checks["auto_update"] = abs(ref.last_update - 10.0) < 1e-6
    print(f"[4] reference auto-updated at t={ref.last_update}")

    # 5) forced interval makes VLM run even on a static scene
    samp2 = AdaptiveSampler(ReferenceFrame(), force_interval=30.0)
    samp2.should_run_vlm(empty, now=0.0)          # warmup True
    static_skip = samp2.should_run_vlm(empty, now=5.0) is False   # within interval, no change
    forced_run = samp2.should_run_vlm(empty, now=31.0) is True    # forced
    checks["forced_interval"] = static_skip and forced_run

    passed = 0
    for k, v in checks.items():
        print(f"   [{'OK' if v else 'XX'}] {k}")
        passed += bool(v)
    print(f"RESULT: {passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
