"""VLMPredicateCompiler — natural language -> structured Predicate.

Hybrid by design:
  1. Fast deterministic rules cover the common, unambiguous conditions
     (counts, postures, zones, absence) in both English and Romanian — instant,
     reliable, no model call.
  2. Anything else falls back to a single text-only VLM call (few-shot prompt)
     that tries to emit a structured predicate.
  3. A templated SEMANTIC predicate is the final safety net, so *every* condition
     compiles even if the small model returns garbage.

The VLM is thus reserved for genuinely abstract conditions ("looks angry",
"unattended bag"), exactly as the brief intends, without ever hard-failing.
"""
from __future__ import annotations

import re
from typing import List, Optional

from backend.predicates.types import EVALUATOR_BY_TYPE, Predicate, PredicateType
from backend.vlm.client import OllamaVLMClient

# ── number words (EN + RO) ───────────────────────────────────────────────
_NUM_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "unu": 1, "una": 1, "doi": 2, "doua": 2, "două": 2, "trei": 3, "patru": 4,
    "cinci": 5, "sase": 6, "șase": 6, "sapte": 7, "șapte": 7, "opt": 8,
    "noua": 9, "nouă": 9, "zece": 10,
}


def _extract_number(text: str, default: int = 1) -> int:
    m = re.search(r"\d+", text)
    if m:
        return int(m.group(0))
    for word, val in _NUM_WORDS.items():
        if re.search(rf"\b{word}\b", text):
            return val
    return default


COMPILER_PROMPT = """You are a compiler for a local camera AI agent.
Given a user's natural-language condition, output ONE JSON predicate the agent
can evaluate on video frames.

Predicate types and evaluators:
- COUNT_GT(value:int) / COUNT_LT(value:int) / COUNT_EQ(value:int)  -> evaluator "yolo"
- PRESENCE_IN_ZONE(zone:str)        -> evaluator "yolo"
- ABSENCE_FOR_DURATION(seconds:int) -> evaluator "yolo"
- POSE_HAND_RAISED / POSE_SITTING / POSE_STANDING -> evaluator "pose"
- SEMANTIC(visual_question:str)     -> evaluator "vlm"  (use for abstract/complex)

For SEMANTIC, write a visual_question the VLM can answer yes/no on a single frame.
Output ONLY JSON: {"type":..., "evaluator":..., "params":{...},
"visual_question":<str or null>, "min_confidence":0-1, "min_consecutive":int,
"cooldown_seconds":int}

Examples:
"More than 5 people in view" -> {"type":"COUNT_GT","evaluator":"yolo","params":{"value":5},"min_confidence":0.8,"min_consecutive":3,"cooldown_seconds":30}
"Fewer than 2 people" -> {"type":"COUNT_LT","evaluator":"yolo","params":{"value":2},"min_confidence":0.8,"min_consecutive":3,"cooldown_seconds":30}
"Someone raises their hand" -> {"type":"POSE_HAND_RAISED","evaluator":"pose","params":{},"min_confidence":0.85,"min_consecutive":3,"cooldown_seconds":30}
"A person is sitting" -> {"type":"POSE_SITTING","evaluator":"pose","params":{},"min_confidence":0.8,"min_consecutive":3,"cooldown_seconds":30}
"Someone enters the pool" -> {"type":"PRESENCE_IN_ZONE","evaluator":"yolo","params":{"zone":"pool"},"min_confidence":0.8,"min_consecutive":3,"cooldown_seconds":30}
"The room is empty for 30 seconds" -> {"type":"ABSENCE_FOR_DURATION","evaluator":"yolo","params":{"seconds":30},"min_confidence":0.8,"min_consecutive":3,"cooldown_seconds":30}
"Someone looks angry" -> {"type":"SEMANTIC","evaluator":"vlm","params":{},"visual_question":"Is any person clearly showing anger (frowning, aggressive posture)? Answer JSON {detected:bool,confidence:0-1,reason:str}","min_confidence":0.85,"min_consecutive":3,"cooldown_seconds":60}

Now compile this condition:
"""


class VLMPredicateCompiler:
    def __init__(self, vlm: OllamaVLMClient, compile_heavy: bool = False) -> None:
        self.vlm = vlm
        self.compile_heavy = compile_heavy  # use the heavier model for VLM fallback

    # ── public ───────────────────────────────────────────────────────────
    def compile(self, text: str, available_zones: Optional[List[str]] = None) -> Predicate:
        rule = self._rule_based(text, available_zones or [])
        if rule is not None:
            return rule
        return self._vlm_compile(text, available_zones or [])

    # ── deterministic rules ──────────────────────────────────────────────
    def _rule_based(self, text: str, zones: List[str]) -> Optional[Predicate]:
        t = text.lower().strip()

        # zone presence (only if a known zone name is mentioned)
        for z in zones:
            if z and z.lower() in t:
                return Predicate(
                    type=PredicateType.PRESENCE_IN_ZONE, params={"zone": z},
                    min_confidence=0.8, original_text=text,
                )

        # hand raised
        if re.search(r"raise|hand up|hands up|ridic|m[aâ]n[aă] sus|m[aâ]na ridicat", t):
            return Predicate(type=PredicateType.POSE_HAND_RAISED, min_confidence=0.85,
                             original_text=text)
        # sitting
        if re.search(r"\bsit(ting|s)?\b|seated|a[sș]ezat|st[aă] jos|st[aă]nd jos", t):
            return Predicate(type=PredicateType.POSE_SITTING, min_confidence=0.8,
                             original_text=text)
        # standing
        if re.search(r"\bstand(ing|s)?\b|[iî]n picioare", t):
            return Predicate(type=PredicateType.POSE_STANDING, min_confidence=0.8,
                             original_text=text)

        # absence for duration
        if re.search(r"no\s*one|nobody|empty|nimeni|gol|nu e nimeni", t):
            secs = _extract_number(t, default=10)
            if re.search(r"min|minut", t):
                secs *= 60
            return Predicate(type=PredicateType.ABSENCE_FOR_DURATION,
                             params={"seconds": secs}, original_text=text)

        # count comparisons
        more = re.search(r"more than|over|at least|greater than|peste|mai mul[tți]|minim", t)
        fewer = re.search(r"fewer than|less than|under|mai pu[țt]in|sub", t)
        has_people = re.search(r"pe(o|r)ple|person|persoan|oameni|cineva|someone|anybody|anyone", t)
        if (more or fewer) and (has_people or re.search(r"\d", t)):
            n = _extract_number(t, default=1)
            if fewer:
                return Predicate(type=PredicateType.COUNT_LT, params={"value": n},
                                 min_confidence=0.8, original_text=text)
            return Predicate(type=PredicateType.COUNT_GT, params={"value": n},
                             min_confidence=0.8, original_text=text)

        return None  # -> VLM fallback

    # ── VLM fallback ─────────────────────────────────────────────────────
    # Only trust the model to *rescue a structural type* the rules missed; for
    # anything semantic/ambiguous we use a clean templated question (small models
    # produce malformed visual_questions, so we don't rely on them for that).
    _STRUCTURAL = {
        "COUNT_GT", "COUNT_LT", "COUNT_EQ", "PRESENCE_IN_ZONE",
        "ABSENCE_FOR_DURATION", "POSE_HAND_RAISED", "POSE_SITTING",
        "POSE_STANDING", "DURATION_IN_ZONE",
    }

    def _vlm_compile(self, text: str, zones: List[str]) -> Predicate:
        # The deterministic rules already catch every genuine structural pattern,
        # so a rule miss means the condition is semantic. We only consult the VLM
        # to *rescue* a structural type when using the capable model (llama3.2-vision
        # via compile_heavy); a small model hallucinates structural types for
        # semantic inputs, so by default we go straight to a clean SEMANTIC.
        if self.compile_heavy:
            zone_info = f"\nAvailable zones: {zones}" if zones else ""
            prompt = COMPILER_PROMPT + f'"{text}"{zone_info}'
            try:
                resp = self.vlm.ask(None, prompt, heavy=True, max_tokens=300)
                data = resp.answer
                if isinstance(data, dict) and "error" not in data:
                    ptype = str(data.get("type", "")).strip().upper()
                    if ptype in self._STRUCTURAL:
                        params = data.get("params")
                        return Predicate(
                            type=ptype,
                            evaluator=data.get("evaluator") or "",
                            params=params if isinstance(params, dict) else {},
                            min_confidence=float(data.get("min_confidence", 0.8) or 0.8),
                            original_text=text,
                        )
            except Exception:
                pass
        # templated SEMANTIC predicate (visual_question filled by the validator)
        return Predicate(type=PredicateType.SEMANTIC, evaluator="vlm",
                         min_confidence=0.8, min_consecutive=3,
                         cooldown_seconds=60, original_text=text)
