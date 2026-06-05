"""Predicate compiler test: 10 conditions (English + Romanian) must all compile
to a valid Predicate with the expected evaluator. SEMANTIC predicates must carry
a visual_question.

Usage:  python scripts/test_compiler.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.predicates.compiler import VLMPredicateCompiler  # noqa: E402
from backend.predicates.types import PredicateType  # noqa: E402
from backend.vlm.client import OllamaVLMClient  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

# (text, expected_evaluator, expected_type_or_None)
CASES = [
    ("More than 5 people in view", "yolo", PredicateType.COUNT_GT),
    ("Someone raises their hand", "pose", PredicateType.POSE_HAND_RAISED),
    ("A person is sitting on the bench", "pose", PredicateType.POSE_SITTING),
    ("Cineva ridica mana", "pose", PredicateType.POSE_HAND_RAISED),          # RO
    ("Mai mult de 3 persoane in cadru", "yolo", PredicateType.COUNT_GT),     # RO
    ("Someone looks angry", "vlm", PredicateType.SEMANTIC),
    ("An unattended bag is left alone", "vlm", PredicateType.SEMANTIC),
    ("Fewer than 2 people", "yolo", PredicateType.COUNT_LT),
    ("O persoana sta jos", "pose", PredicateType.POSE_SITTING),              # RO
    ("A person is lying on the floor", "vlm", PredicateType.SEMANTIC),
]


def main() -> int:
    vlm = OllamaVLMClient()
    comp = VLMPredicateCompiler(vlm)

    passed = 0
    for text, exp_eval, exp_type in CASES:
        p = comp.compile(text)
        eval_ok = p.evaluator == exp_eval
        type_ok = (exp_type is None) or (p.type == exp_type.value)
        sem_ok = (not p.is_semantic) or bool(p.visual_question)
        ok = eval_ok and type_ok and sem_ok
        passed += ok
        vq = (p.visual_question or "")[:40]
        print(f"[{'OK' if ok else 'XX'}] {text!r:42s} -> type={p.type} eval={p.evaluator} "
              f"params={p.params}" + (f" vq='{vq}...'" if p.is_semantic else ""))

    # demonstrate the VLM-compile path with the capable model (non-gating)
    print("\n[heavy] VLM-compile path (llama3.2-vision) on an unusual phrasing:")
    heavy = VLMPredicateCompiler(vlm, compile_heavy=True)
    demo = heavy.compile("the area stays completely empty for half a minute")
    print(f"   -> type={demo.type} eval={demo.evaluator} params={demo.params} "
          f"valid={bool(demo.type)}")

    print(f"\nRESULT: {passed}/{len(CASES)} compiled correctly")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
