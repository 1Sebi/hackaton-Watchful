"""Confidence threshold gate — reject weak or negative detections.

Mechanism 1 of the anti-false-positive layer: a detection only counts if it is
positive *and* its confidence clears the predicate's ``min_confidence``.
"""
from __future__ import annotations


class ThresholdGate:
    def passes(self, result, predicate) -> bool:
        """``result`` has .detected/.confidence; ``predicate`` has .min_confidence."""
        return bool(getattr(result, "detected", False)) and (
            float(getattr(result, "confidence", 0.0)) >= float(predicate.min_confidence)
        )
