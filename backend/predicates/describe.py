"""Human-readable explanation of a compiled Predicate.

The compiler turns natural language into a structured Predicate, but a non-technical
user can't tell whether "COUNT_GT via yolo" is what they meant — or whether their
phrasing quietly fell through to the open-ended VLM path. This module renders a
plain-language summary plus a reliability tier so the editor can show, BEFORE saving:

  ✅ precise  — deterministic check (count / pose / presence / absence) on YOLO/pose.
  ⚠️ visual   — an open-ended question answered by the local VLM each frame.

This is half of "make it doable": you see what your text became, not a black box.
"""
from __future__ import annotations

from typing import Any, Dict

from backend.predicates.types import Predicate, PredicateType

# deterministic types run on YOLO/pose geometry — reliable, high-fps, no hallucination
_PRECISE = {
    PredicateType.COUNT_GT.value,
    PredicateType.COUNT_LT.value,
    PredicateType.COUNT_EQ.value,
    PredicateType.PRESENCE_IN_ZONE.value,
    PredicateType.ABSENCE_FOR_DURATION.value,
    PredicateType.DURATION_IN_ZONE.value,
    PredicateType.POSE_HAND_RAISED.value,
    PredicateType.POSE_SITTING.value,
    PredicateType.POSE_STANDING.value,
}


def _humanize_secs(secs: int) -> str:
    secs = int(secs)
    if secs % 3600 == 0 and secs >= 3600:
        h = secs // 3600
        return f"{h} hour" + ("s" if h != 1 else "")
    if secs % 60 == 0 and secs >= 60:
        m = secs // 60
        return f"{m} minute" + ("s" if m != 1 else "")
    return f"{secs} second" + ("s" if secs != 1 else "")


def describe_predicate(pred: Any) -> Dict[str, Any]:
    """Return {summary, reliability, reliable, warnings} for a Predicate or its dict."""
    if isinstance(pred, Predicate):
        pred = pred.model_dump()
    ptype = str(pred.get("type", ""))
    params = pred.get("params") or {}
    text = pred.get("original_text") or ""
    warnings: list[str] = []

    if ptype == PredicateType.COUNT_GT.value:
        v = int(params.get("value", 0))
        if v <= 0:
            summary = "Fires when at least one person is visible."
        else:
            summary = f"Fires when more than {v} people are visible."
    elif ptype == PredicateType.COUNT_LT.value:
        v = int(params.get("value", 0))
        summary = f"Fires when fewer than {v} people are visible."
    elif ptype == PredicateType.COUNT_EQ.value:
        v = int(params.get("value", 0))
        summary = f"Fires when exactly {v} {'person is' if v == 1 else 'people are'} visible."
    elif ptype == PredicateType.PRESENCE_IN_ZONE.value:
        zone = params.get("zone") or "the zone"
        summary = f"Fires when someone is inside the '{zone}' zone."
    elif ptype == PredicateType.ABSENCE_FOR_DURATION.value:
        summary = f"Fires when no one is seen for {_humanize_secs(params.get('seconds', 10))}."
    elif ptype == PredicateType.POSE_HAND_RAISED.value:
        summary = "Fires when someone raises a hand."
    elif ptype == PredicateType.POSE_SITTING.value:
        summary = "Fires when someone is sitting."
    elif ptype == PredicateType.POSE_STANDING.value:
        summary = "Fires when someone is standing."
    elif ptype == PredicateType.DURATION_IN_ZONE.value:
        zone = params.get("zone") or "the zone"
        summary = f"Fires when someone stays in '{zone}' long enough."
    else:  # SEMANTIC / unknown -> VLM
        q = (text or "the described situation").strip().rstrip(".")
        summary = f"The local AI vision model watches each frame and decides if: “{q}”."
        warnings.append(
            "Open-ended visual check — handled by the local vision model (Ollama), "
            "so it's slower (~1 fps) and less certain than counting or pose. Keep it "
            "short and visually obvious, and make sure the vision model is running."
        )

    reliable = ptype in _PRECISE
    return {
        "summary": summary,
        "reliability": "precise" if reliable else "visual",
        "reliable": reliable,
        "warnings": warnings,
    }
