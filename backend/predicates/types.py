"""Predicate types — the structured, checkable form of a natural-language condition.

A ``Predicate`` is what the VLM/rule compiler emits and what the agent loop
evaluates each frame. ``evaluator`` decides which engine checks it:
``yolo`` (counts/zones), ``pose`` (postures), ``vlm`` (semantic), ``hybrid``.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PredicateType(str, Enum):
    COUNT_GT = "COUNT_GT"
    COUNT_LT = "COUNT_LT"
    COUNT_EQ = "COUNT_EQ"
    PRESENCE_IN_ZONE = "PRESENCE_IN_ZONE"
    ABSENCE_FOR_DURATION = "ABSENCE_FOR_DURATION"
    DURATION_IN_ZONE = "DURATION_IN_ZONE"
    POSE_HAND_RAISED = "POSE_HAND_RAISED"
    POSE_SITTING = "POSE_SITTING"
    POSE_STANDING = "POSE_STANDING"
    SEMANTIC = "SEMANTIC"


# default evaluator routing per predicate type (keyed by str value)
EVALUATOR_BY_TYPE: Dict[str, str] = {
    PredicateType.COUNT_GT.value: "yolo",
    PredicateType.COUNT_LT.value: "yolo",
    PredicateType.COUNT_EQ.value: "yolo",
    PredicateType.PRESENCE_IN_ZONE.value: "yolo",
    PredicateType.ABSENCE_FOR_DURATION.value: "yolo",
    PredicateType.DURATION_IN_ZONE.value: "hybrid",
    PredicateType.POSE_HAND_RAISED.value: "pose",
    PredicateType.POSE_SITTING.value: "pose",
    PredicateType.POSE_STANDING.value: "pose",
    PredicateType.SEMANTIC.value: "vlm",
}


class Predicate(BaseModel):
    """A compiled, evaluable condition. Tolerant of extra fields from the VLM."""

    model_config = ConfigDict(extra="ignore", use_enum_values=True)

    type: PredicateType
    evaluator: str = ""
    params: Dict[str, Any] = Field(default_factory=dict)
    visual_question: Optional[str] = None
    min_confidence: float = 0.7
    min_consecutive: int = 3
    cooldown_seconds: int = 30
    original_text: str = ""

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, v: Any) -> Any:
        if isinstance(v, PredicateType):
            return v
        if isinstance(v, str):
            try:
                return PredicateType(v.strip().upper())
            except ValueError:
                return PredicateType.SEMANTIC  # unknown -> treat as semantic
        return PredicateType.SEMANTIC

    @model_validator(mode="after")
    def _fill_defaults(self) -> "Predicate":
        # route to default evaluator when the compiler didn't supply one
        if not self.evaluator:
            self.evaluator = EVALUATOR_BY_TYPE.get(self.type, "vlm")
        # a SEMANTIC predicate must carry a question for the VLM evaluator
        if self.type == PredicateType.SEMANTIC.value and not self.visual_question:
            text = self.original_text or "the described condition"
            self.visual_question = (
                f"Looking only at this image, is the following condition currently true: "
                f"\"{text}\"? Be conservative — if unsure, say no. "
                'Answer JSON: {"detected": <true|false>, "confidence": <0.0-1.0>, "reason": "<short>"}'
            )
        return self

    @property
    def is_semantic(self) -> bool:
        return self.type == PredicateType.SEMANTIC.value
