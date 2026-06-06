"""HybridEvaluator — routes a Predicate to the right engine each frame.

  evaluator == "yolo"  -> counts / presence-in-zone / absence (deterministic)
  evaluator == "pose"  -> hand raised / sitting / standing (geometric)
  evaluator == "vlm"   -> semantic question answered by the local VLM
  evaluator == "hybrid"-> duration-in-zone (yolo presence + dwell time)

The VLM path is *adaptively sampled*: at most ``vlm_max_fps`` calls per predicate;
in-between frames reuse the last result. This keeps the expensive model off the
hot path while YOLO/Pose run every frame.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from backend.core.detector import Detection
from backend.core.pose_analyzer import Pose, PoseAnalyzer
from backend.core.tracker import Track
from backend.predicates.types import Predicate, PredicateType
from backend.vlm.client import OllamaVLMClient


# ── per-frame perception bundle ──────────────────────────────────────────
@dataclass
class EvalContext:
    frame: Optional[np.ndarray] = None
    detections: List[Detection] = field(default_factory=list)
    poses: List[Pose] = field(default_factory=list)
    pose_map: Dict[int, Pose] = field(default_factory=dict)  # track_id -> Pose
    tracks: Dict[int, Track] = field(default_factory=dict)
    zones: Dict[str, list] = field(default_factory=dict)     # name -> [(x,y), ...]
    now: float = 0.0
    camera_id: str = ""  # scopes per-camera state (absence timer, VLM cache)


@dataclass
class EvalResult:
    detected: bool
    confidence: float
    reason: str = ""
    evaluator: str = ""
    matched_track_ids: List[int] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


def _point_in_poly(point: Tuple[int, int], poly: list) -> bool:
    if not poly or len(poly) < 3:
        return False
    arr = np.array(poly, dtype=np.int32)
    return cv2.pointPolygonTest(arr, (float(point[0]), float(point[1])), False) >= 0


def _parse_detected(a: dict) -> Tuple[bool, float, str]:
    """Lenient parse of a VLM yes/no JSON answer (handles varied key names)."""
    if not isinstance(a, dict):
        return False, 0.0, ""
    det = False
    for k in ("detected", "present", "result", "answer", "value", "yes"):
        if k in a:
            v = a[k]
            if isinstance(v, bool):
                det = v
            elif isinstance(v, (int, float)):
                det = v > 0
            elif isinstance(v, str):
                det = v.strip().lower() in ("yes", "true", "1", "y", "present")
            else:
                det = bool(v)
            break
    conf = a.get("confidence", 1.0 if det else 0.0)
    try:
        conf = float(conf)
    except (TypeError, ValueError):
        conf = 1.0 if det else 0.0
    return det, conf, str(a.get("reason", ""))


class HybridEvaluator:
    def __init__(
        self,
        pose_analyzer: Optional[PoseAnalyzer] = None,
        vlm: Optional[OllamaVLMClient] = None,
        vlm_max_fps: float = 1.0,
    ) -> None:
        self.pose = pose_analyzer
        self.vlm = vlm
        self.vlm_min_interval = 1.0 / vlm_max_fps if vlm_max_fps > 0 else 0.0
        self._vlm_cache: Dict[str, Tuple[float, EvalResult]] = {}
        self._absence_last_present: Dict[str, float] = {}
        self.vlm_calls = 0  # for tests / metrics

    @staticmethod
    def _key(p: Predicate) -> str:
        return f"{p.type}|{p.original_text}|{p.visual_question}"

    # ── routing ──────────────────────────────────────────────────────────
    def evaluate(self, predicate: Predicate, ctx: EvalContext) -> EvalResult:
        ev = predicate.evaluator
        if ev == "yolo":
            return self._yolo(predicate, ctx)
        if ev == "pose":
            return self._pose(predicate, ctx)
        if ev == "hybrid":
            return self._yolo(predicate, ctx)  # duration-in-zone handled via yolo+dwell
        return self._vlm(predicate, ctx)

    # ── YOLO: counts / presence / absence ────────────────────────────────
    def _scope_dets(self, predicate: Predicate, ctx: EvalContext) -> List[Detection]:
        zone = predicate.params.get("zone")
        if zone and zone in ctx.zones:
            poly = ctx.zones[zone]
            return [d for d in ctx.detections if _point_in_poly(d.center, poly)]
        return list(ctx.detections)

    def _yolo(self, predicate: Predicate, ctx: EvalContext) -> EvalResult:
        t = predicate.type
        if t == PredicateType.ABSENCE_FOR_DURATION.value:
            return self._absence(predicate, ctx)

        dets = self._scope_dets(predicate, ctx)
        count = len(dets)
        ids = [d.track_id for d in dets if d.track_id is not None]
        avg_conf = float(np.mean([d.conf for d in dets])) if dets else 0.0

        # Counts/presence are DETERMINISTIC: when the count clears the threshold we
        # are certain (confidence 1.0). Per-detection avg_conf only reflects YOLO box
        # quality, not count certainty — gating a count on it (vs min_confidence 0.8)
        # silently blocked every count rule once the detector conf was lowered. The
        # debounce (N consecutive) + cooldown still guard against flukes.
        if t == PredicateType.COUNT_GT.value:
            v = int(predicate.params.get("value", 0))
            det = count > v
            return EvalResult(det, 1.0 if det else 0.0, f"count {count} > {v}", "yolo", ids,
                              {"count": count, "avg_conf": round(avg_conf, 2)})
        if t == PredicateType.COUNT_LT.value:
            v = int(predicate.params.get("value", 0))
            det = count < v
            return EvalResult(det, 1.0 if det else 0.0, f"count {count} < {v}", "yolo", ids, {"count": count})
        if t == PredicateType.COUNT_EQ.value:
            v = int(predicate.params.get("value", 0))
            det = count == v
            return EvalResult(det, 1.0 if det else 0.0,
                              f"count {count} == {v}", "yolo", ids, {"count": count})
        if t == PredicateType.PRESENCE_IN_ZONE.value:
            det = count > 0
            return EvalResult(det, 1.0 if det else 0.0,
                              f"{count} in zone {predicate.params.get('zone')}", "yolo", ids,
                              {"count": count, "avg_conf": round(avg_conf, 2)})
        return EvalResult(False, 0.0, f"unhandled yolo type {t}", "yolo")

    def _absence(self, predicate: Predicate, ctx: EvalContext) -> EvalResult:
        key = f"{ctx.camera_id}|{self._key(predicate)}"  # per-camera absence timer
        secs = int(predicate.params.get("seconds", 10))
        if ctx.detections:
            self._absence_last_present[key] = ctx.now
            return EvalResult(False, 0.0, "people present", "yolo", extra={"elapsed": 0.0})
        last = self._absence_last_present.setdefault(key, ctx.now)
        elapsed = ctx.now - last
        det = elapsed >= secs
        return EvalResult(det, 1.0 if det else 0.0, f"empty {elapsed:.0f}s/{secs}s", "yolo",
                          extra={"elapsed": elapsed})

    # ── Pose: hand raised / sitting / standing ───────────────────────────
    def _pose(self, predicate: Predicate, ctx: EvalContext) -> EvalResult:
        if self.pose is None:
            return EvalResult(False, 0.0, "no pose analyzer", "pose")
        fn = {
            PredicateType.POSE_HAND_RAISED.value: self.pose.is_hand_raised,
            PredicateType.POSE_SITTING.value: self.pose.is_sitting,
            PredicateType.POSE_STANDING.value: self.pose.is_standing,
        }.get(predicate.type)
        if fn is None:
            return EvalResult(False, 0.0, f"unhandled pose type {predicate.type}", "pose")

        items = list(ctx.pose_map.items()) if ctx.pose_map else [(None, p) for p in ctx.poses]
        detected, conf, matched = False, 0.0, []
        for tid, p in items:
            if fn(p):
                detected = True
                conf = max(conf, p.conf)
                if tid is not None:
                    matched.append(tid)
        return EvalResult(detected, conf if detected else 0.0,
                          f"{predicate.type}={detected}", "pose", matched)

    # ── VLM: semantic, adaptively sampled ────────────────────────────────
    def _crop_for(self, predicate: Predicate, ctx: EvalContext) -> Optional[np.ndarray]:
        if ctx.frame is None or not predicate.params.get("crop") or not ctx.detections:
            return ctx.frame  # default: full frame (works for scene + person questions)
        d = max(ctx.detections, key=lambda d: d.area)
        x1, y1, x2, y2 = d.bbox
        h, w = ctx.frame.shape[:2]
        pad = int(0.15 * max(x2 - x1, y2 - y1))
        x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
        x2, y2 = min(w, x2 + pad), min(h, y2 + pad)
        return ctx.frame[y1:y2, x1:x2]

    def _vlm(self, predicate: Predicate, ctx: EvalContext) -> EvalResult:
        key = f"{ctx.camera_id}|{self._key(predicate)}"  # per-camera VLM cache
        cached = self._vlm_cache.get(key)
        if cached and (ctx.now - cached[0]) < self.vlm_min_interval:
            return cached[1]  # adaptive sampling: reuse recent result
        if self.vlm is None or ctx.frame is None:
            return EvalResult(False, 0.0, "no vlm/frame", "vlm")

        crop = self._crop_for(predicate, ctx)
        question = predicate.visual_question or (
            'Is the described condition true in this image? '
            'Answer JSON {"detected": bool, "confidence": 0-1, "reason": str}'
        )
        heavy = bool(predicate.params.get("heavy", False))
        resp = self.vlm.ask(crop, question, heavy=heavy, max_tokens=120)
        self.vlm_calls += 1
        det, conf, reason = _parse_detected(resp.answer)
        res = EvalResult(det, conf, reason, "vlm", extra={"latency_ms": resp.latency_ms})
        self._vlm_cache[key] = (ctx.now, res)
        return res
