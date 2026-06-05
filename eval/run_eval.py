"""Watchful evaluation harness.

Loads eval/ground_truth.json, runs each case through the real compile + evaluate
+ anti-false-positive decision, compares to expected, and reports a confusion
matrix with precision / recall / F1 (overall + per category). Writes results.md.

Frame cases: compile the condition, run detector/pose on the source image (or a
synthetic empty frame), evaluate the predicate, and apply the threshold gate as
the single-frame fire decision.
Stream cases: drive the anti-false-positive layer with a temporal pattern
(steady / flicker / absence) — this is where "the hard part" is measured.

Usage:  python eval/run_eval.py
"""
from __future__ import annotations

import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.antifalse import AntiFalsePositive  # noqa: E402
from backend.antifalse.threshold import ThresholdGate  # noqa: E402
from backend.core.detector import PersonDetector  # noqa: E402
from backend.core.pose_analyzer import PoseAnalyzer  # noqa: E402
from backend.predicates.compiler import VLMPredicateCompiler  # noqa: E402
from backend.predicates.evaluator import EvalContext, EvalResult, HybridEvaluator  # noqa: E402
from backend.predicates.types import Predicate  # noqa: E402
from backend.vlm.client import OllamaVLMClient  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


class _R:
    def __init__(self, detected, confidence):
        self.detected = detected
        self.confidence = confidence


def _frames():
    from ultralytics import ASSETS

    empty = np.full((480, 640, 3), 60, dtype=np.uint8)
    return {
        "bus.jpg": cv2.imread(str(ASSETS / "bus.jpg")),
        "zidane.jpg": cv2.imread(str(ASSETS / "zidane.jpg")),
        "empty": empty,
    }


def _decide_frame(case, ctx_cache, det, pose, evaluator, compiler, gate) -> bool:
    src = case["source"]
    if src not in ctx_cache:
        img = _frames()[src]
        dets = det.detect_and_track(img.copy())
        poses = pose.analyze(img)
        pmap = pose.associate(poses, dets)
        ctx_cache[src] = EvalContext(frame=img, detections=dets, poses=poses,
                                     pose_map=pmap, now=1000.0)
    ctx = ctx_cache[src]
    pred: Predicate = compiler.compile(case["condition"])
    if case.get("heavy") and pred.is_semantic:
        pred.params["heavy"] = True
    result = evaluator.evaluate(pred, ctx)
    return gate.passes(result, pred)


def _decide_stream(case) -> bool:
    pattern = case["pattern"]
    afp = AntiFalsePositive()
    pred = Predicate(type="COUNT_GT", params={"value": 0}, min_confidence=0.7,
                     min_consecutive=3, cooldown_seconds=30, original_text=case["id"])
    fired = False
    if pattern == "steady":
        for t in range(6):
            f, _ = afp.should_fire(pred, _R(True, 0.95), now=float(t))
            fired = fired or f
    elif pattern == "flicker":
        seq = [True, True, False] * 6  # never 3 consecutive
        for t, p in enumerate(seq):
            f, _ = afp.should_fire(pred, _R(p, 0.95), now=float(t))
            fired = fired or f
    elif pattern == "absence":
        # absence becomes true after 2s empty; needs 3 consecutive -> fire
        for t in (0.0, 2.2, 2.4, 2.6):
            detected = t >= 2.0
            f, _ = afp.should_fire(pred, _R(detected, 1.0 if detected else 0.0), now=t)
            fired = fired or f
    return fired


def main() -> int:
    gt = json.load(open(os.path.join(HERE, "ground_truth.json"), encoding="utf-8"))
    cases = gt["cases"]

    det = PersonDetector()
    pose = PoseAnalyzer()
    vlm = OllamaVLMClient()
    evaluator = HybridEvaluator(pose, vlm, vlm_max_fps=1000)  # no throttle during eval
    compiler = VLMPredicateCompiler(vlm)
    gate = ThresholdGate()
    ctx_cache: dict = {}

    tp = fp = tn = fn = 0
    by_cat: dict = {}
    rows = []
    for c in cases:
        fired = _decide_stream(c) if c["mode"] == "stream" else \
            _decide_frame(c, ctx_cache, det, pose, evaluator, compiler, gate)
        exp = bool(c["expected"])
        ok = fired == exp
        if exp and fired:
            tp += 1
        elif (not exp) and fired:
            fp += 1
        elif (not exp) and (not fired):
            tn += 1
        else:
            fn += 1
        cat = by_cat.setdefault(c["category"], {"ok": 0, "n": 0})
        cat["n"] += 1
        cat["ok"] += int(ok)
        rows.append((c["id"], c["category"], c["condition"][:34], exp, fired, ok))
        print(f"  [{'OK' if ok else 'XX'}] {c['id']:3s} {c['category']:7s} exp={int(exp)} fired={int(fired)}  {c['condition'][:40]}")

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    accuracy = (tp + tn) / len(cases)
    false_trigger_rate = fp / (fp + tn) if (fp + tn) else 0.0

    print("\n=== CONFUSION ===")
    print(f"TP={tp} FP={fp} TN={tn} FN={fn}")
    print(f"precision={precision:.3f} recall={recall:.3f} F1={f1:.3f} acc={accuracy:.3f} false_trigger_rate={false_trigger_rate:.3f}")

    _write_results(rows, tp, fp, tn, fn, precision, recall, f1, accuracy, false_trigger_rate, by_cat)
    print(f"\nwrote {os.path.join(HERE, 'results.md')}")
    print("CALIBRATION", "PASS (precision > 0.90)" if precision > 0.90 else "FAIL")
    return 0 if precision > 0.90 else 1


def _write_results(rows, tp, fp, tn, fn, precision, recall, f1, accuracy, ftr, by_cat) -> None:
    lines = ["# Watchful — Evaluation Results", ""]
    lines.append(f"**Cases:** {len(rows)}  ·  **Precision:** {precision:.1%}  ·  "
                 f"**Recall:** {recall:.1%}  ·  **F1:** {f1:.1%}  ·  **Accuracy:** {accuracy:.1%}")
    lines.append("")
    lines.append(f"**False-trigger rate (FP / negatives):** {ftr:.1%}  "
                 f"— the metric that matters most ('don't fire on shadows').")
    lines.append("")
    lines.append(f"Confusion: TP={tp} · FP={fp} · TN={tn} · FN={fn}")
    lines.append("")
    lines.append("Per category (accuracy):")
    for cat, v in by_cat.items():
        lines.append(f"- **{cat}**: {v['ok']}/{v['n']}")
    lines.append("")
    lines.append("| id | category | condition | expected | fired | ok |")
    lines.append("|---|---|---|---|---|---|")
    for rid, cat, cond, exp, fired, ok in rows:
        lines.append(f"| {rid} | {cat} | {cond} | {int(exp)} | {int(fired)} | {'✓' if ok else '✗'} |")
    lines.append("")
    lines.append("> Eval set = ultralytics bundled images (bus.jpg, zidane.jpg) + a synthetic "
                 "empty frame + AFP trap/steady/absence streams. Semantic cases use the heavy "
                 "local VLM (llama3.2-vision). On-site venue clips are a known follow-up.")
    with open(os.path.join(HERE, "results.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
