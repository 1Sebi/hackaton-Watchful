# 🎯 Calibration findings — `person_present` on REAL ThePlace footage

> Produced on the venue-LAN machine (parallel hardware lane). 14 real ~6s clips
> from both NVRs, sub-stream 640x360. Ground truth = human-labeled, then
> **verified frame-by-frame** against detections. Clips gitignored; this report
> and `run_eval.py` / `ground_truth.json` are the shareable artifacts.

## Model/threshold sweep

| config | Precision | Recall | F1 | Acc | what breaks |
|---|---|---|---|---|---|
| yolov8n @0.50, mf2 | **1.00** | 0.60 | 0.75 | 0.86 | misses seated/distant diners (0/8) |
| yolov8n @0.25, mf2 | 0.57 | 0.80 | 0.67 | 0.71 | traps start firing (cars/reflections) |
| yolov8s @0.40, mf2 | 0.83 | 0.83 | 0.83 | 0.86 | restaurant_b still missed |
| **yolov8m @0.40, mf2** | **0.857** | **1.00** | **0.923** | **0.929** | 1 FP: glass reflection |

`mf2` = predicate fires only if a person appears in ≥2 of 8 sampled frames
(temporal debounce — brief AFP #1).

## Findings (real-world, can't be gotten in the cloud)

1. **yolov8n is too weak for this venue.** High overhead angles + people *seated*
   in low light at 640x360 → nano detects nothing (0/8 on both restaurant clips).
   Recall is **model-size-bound, not threshold-bound**: lowering conf to recover
   recall just makes traps fire (precision 1.00→0.57). **Use yolov8m** (or feed a
   higher-res crop). This contradicts the "drop to yolov8n for FPS" note in
   PROGRESS PAS 3 — for accuracy you need ≥ yolov8m here.

2. **The eval caught a ground-truth labeling error.** `lobby_bar2` was eyeballed
   as "empty" but the model found a bartender behind the counter — confirmed by
   frame inspection. The human was wrong, the model was right. → always verify
   detections against frames before trusting labels.

3. **The last false positive can't be fixed by a threshold.** The glass-reflection
   FP (`east_exit_glass`, conf 0.42, 2/8) sits at the *same* difficulty as a real
   distant diner (`restaurant_a`, conf 0.45, 2/8). No conf/frame cutoff separates
   them. **This is the real-data justification for ZONE MASKING (brief AFP #4):**
   mask the glass-door / reflective region and the FP disappears with no recall
   loss → expected **Precision → ~100%**.

4. **CPU FPS vs accuracy tension — resolved by adaptive sampling.** yolov8m on
   CPU is slow for 25 FPS, but presence/count doesn't need 25 FPS. Run detection
   at ~2–5 FPS (brief's adaptive sampler, PAS 7) → yolov8m is affordable AND
   accurate. Don't trade accuracy for a frame rate the task doesn't need.

## Recommended production config for presence/count

```
model        = yolov8m.pt
person_conf  = 0.40
debounce     = person in >= 2 of N sampled frames
zone_mask    = exclude reflective glass regions (east exit) + parking edges
sampling     = ~3 FPS for detection (adaptive), not 25
```
Expected on this set with the glass zone masked: **P ≈ 100%, R = 100%**.

## How to reproduce
```
python eval/run_eval.py --model yolov8m.pt --conf 0.4 --min-frames 2 --samples 8
# clips live in eval/clips/ambient/ (gitignored) — re-record with scripts/batch_record.py
```
