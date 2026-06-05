"""Visualizer — render the agent's perception onto a frame for the live MJPEG view.

draw_overlay() composites, in order: semi-transparent zone polygons, alpha-faded
track trails, pose skeletons, per-track colored bboxes with "#id Xs [HAND]" labels,
and a HUD bar (FPS / persons / conditions / last trigger). The pipeline imports
this automatically; a basic fallback lives inline in pipeline.py.
"""
from __future__ import annotations

import cv2
import numpy as np

from backend.core.pose_analyzer import COCO_SKELETON, KP_INDEX

PALETTE = [
    (0, 255, 0), (255, 128, 0), (0, 128, 255), (255, 0, 255),
    (0, 255, 255), (0, 165, 255), (255, 255, 0), (128, 0, 255),
]
_KP_THR = 0.3


def _color(track_id):
    return PALETTE[(track_id or 0) % len(PALETTE)]


def _hand_raised(pose) -> bool:
    for side in ("left", "right"):
        sh = pose.keypoints[KP_INDEX[f"{side}_shoulder"]]
        wr = pose.keypoints[KP_INDEX[f"{side}_wrist"]]
        if sh[2] > _KP_THR and wr[2] > _KP_THR and wr[1] < sh[1]:
            return True
    return False


def _draw_zones(img, zones):
    if not zones:
        return
    overlay = img.copy()
    for name, poly in zones.items():
        if not poly or len(poly) < 3:
            continue
        arr = np.array(poly, np.int32)
        cv2.fillPoly(overlay, [arr], (90, 70, 200))
        cv2.polylines(img, [arr], True, (120, 90, 255), 2)
        cx, cy = arr.mean(axis=0).astype(int)
        cv2.putText(img, str(name), (int(cx) - 10, int(cy)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.addWeighted(overlay, 0.25, img, 0.75, 0, img)


def _draw_trails(img, tracker):
    if tracker is None:
        return
    overlay = img.copy()
    for tid, t in tracker.tracks.items():
        pts = list(t.positions)
        col = _color(tid)
        for i in range(1, len(pts)):
            cv2.line(overlay, tuple(map(int, pts[i - 1])), tuple(map(int, pts[i])), col, 2)
    cv2.addWeighted(overlay, 0.5, img, 0.5, 0, img)


def _draw_skeletons(img, pose_map):
    for pose in (pose_map or {}).values():
        kps = pose.keypoints
        for a, b in COCO_SKELETON:
            if kps[a][2] > _KP_THR and kps[b][2] > _KP_THR:
                cv2.line(img, (int(kps[a][0]), int(kps[a][1])),
                         (int(kps[b][0]), int(kps[b][1])), (0, 255, 180), 2)
        for x, y, c in kps:
            if c > _KP_THR:
                cv2.circle(img, (int(x), int(y)), 3, (0, 90, 255), -1)


def _draw_hud(img, state):
    h, w = img.shape[:2]
    state = state or {}
    cv2.rectangle(img, (0, 0), (w, 30), (20, 20, 20), -1)
    txt = (f"WATCHFUL   FPS {state.get('fps', 0):.0f}   AI {state.get('detect_fps', 0):.0f}/s   "
           f"persons {state.get('persons', 0)}   conditions {state.get('conditions', 0)}")
    cv2.putText(img, txt, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 170), 2)
    le = state.get("last_event")
    if le:
        bar = f"LAST: {str(le.get('text', ''))[:44]}"
        cv2.rectangle(img, (0, h - 26), (w, h), (0, 0, 0), -1)
        cv2.putText(img, bar, (8, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 2)


def draw_overlay(frame, dets, pose_map, tracker=None, state=None, zones=None):
    img = frame.copy()
    _draw_zones(img, zones)
    _draw_trails(img, tracker)
    _draw_skeletons(img, pose_map)
    for d in dets:
        x1, y1, x2, y2 = d.bbox
        col = _color(d.track_id)
        cv2.rectangle(img, (x1, y1), (x2, y2), col, 2)
        dur = tracker.duration_of(d.track_id) if (tracker and d.track_id) else 0.0
        label = f"#{d.track_id} {dur:.0f}s"
        pose = (pose_map or {}).get(d.track_id) if d.track_id else None
        if pose is not None and _hand_raised(pose):
            label += " HAND^"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        cv2.rectangle(img, (x1, max(0, y1 - th - 8)), (x1 + tw + 6, y1), col, -1)
        cv2.putText(img, label, (x1 + 3, max(12, y1 - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)
    _draw_hud(img, state)
    return img
