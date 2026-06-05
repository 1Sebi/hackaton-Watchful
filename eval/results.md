# Watchful — Evaluation Results

**Cases:** 30  ·  **Precision:** 100.0%  ·  **Recall:** 90.0%  ·  **F1:** 94.7%  ·  **Accuracy:** 96.7%

**False-trigger rate (FP / negatives):** 0.0%  — the metric that matters most ('don't fire on shadows').

Confusion: TP=9 · FP=0 · TN=20 · FN=1

Per category (accuracy):
- **true**: 9/10
- **trap**: 10/10
- **neutral**: 10/10

| id | category | condition | expected | fired | ok |
|---|---|---|---|---|---|
| T1 | true | more than 2 people | 1 | 1 | ✓ |
| T2 | true | more than 1 person | 1 | 1 | ✓ |
| T3 | true | fewer than 5 people | 1 | 1 | ✓ |
| T4 | true | someone is standing | 1 | 1 | ✓ |
| T5 | true | fewer than 10 people | 1 | 1 | ✓ |
| T6 | true | more than 1 person | 1 | 1 | ✓ |
| T7 | true | fewer than 4 people | 1 | 1 | ✓ |
| T8 | true | is there a bus in this image | 1 | 0 | ✗ |
| T9 | true | sustained positive | 1 | 1 | ✓ |
| T10 | true | no one present for 2 seconds | 1 | 1 | ✓ |
| P1 | trap | more than 5 people | 0 | 0 | ✓ |
| P2 | trap | more than 10 people | 0 | 0 | ✓ |
| P3 | trap | someone raises their hand | 0 | 0 | ✓ |
| P4 | trap | someone is sitting | 0 | 0 | ✓ |
| P5 | trap | more than 3 people | 0 | 0 | ✓ |
| P6 | trap | more than 5 people | 0 | 0 | ✓ |
| P7 | trap | someone raises their hand | 0 | 0 | ✓ |
| P8 | trap | someone is sitting | 0 | 0 | ✓ |
| P9 | trap | 2-frame flicker (debounce must sup | 0 | 0 | ✓ |
| P10 | trap | is there a snowy mountain in this  | 0 | 0 | ✓ |
| N1 | neutral | more than 0 people | 0 | 0 | ✓ |
| N2 | neutral | more than 1 person | 0 | 0 | ✓ |
| N3 | neutral | more than 2 people | 0 | 0 | ✓ |
| N4 | neutral | more than 5 people | 0 | 0 | ✓ |
| N5 | neutral | someone is standing | 0 | 0 | ✓ |
| N6 | neutral | someone is sitting | 0 | 0 | ✓ |
| N7 | neutral | someone raises their hand | 0 | 0 | ✓ |
| N8 | neutral | more than 3 people | 0 | 0 | ✓ |
| N9 | neutral | is there a person in this image | 0 | 0 | ✓ |
| N10 | neutral | is there a dog in this image | 0 | 0 | ✓ |

> Eval set = ultralytics bundled images (bus.jpg, zidane.jpg) + a synthetic empty frame + AFP trap/steady/absence streams. Semantic cases use the heavy local VLM (llama3.2-vision). On-site venue clips are a known follow-up.
