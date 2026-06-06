"""TrackManager — per-track state on top of the detector's track ids.

Accumulates position history (for trails), how long each person has been present
(for duration predicates like "loitering > 30s"), prunes tracks that vanished,
and exposes a live ``active_count``. Time is injectable so the logic is testable
without real clocks.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

from backend.core.detector import Detection


@dataclass
class Track:
    track_id: int
    bbox: Tuple[int, int, int, int]
    first_seen: float
    last_seen: float
    positions: Deque[Tuple[int, int]] = field(default_factory=lambda: deque(maxlen=64))

    @property
    def duration(self) -> float:
        """Seconds this track has been continuously present."""
        return max(0.0, self.last_seen - self.first_seen)

    @property
    def center(self) -> Optional[Tuple[int, int]]:
        return self.positions[-1] if self.positions else None


def _iou(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0.0


class TrackManager:
    def __init__(self, max_history: int = 64, prune_after: float = 5.0) -> None:
        self.tracks: Dict[int, Track] = {}
        self.max_history = max_history
        self.prune_after = prune_after  # seconds since last_seen before forgetting
        # used by update_iou to mint fresh ids when no ByteTrack id is supplied
        self._next_id = 1

    def update(self, detections: List[Detection], now: Optional[float] = None) -> Dict[int, Track]:
        """Fold this frame's detections into track state; prune stale tracks."""
        now = time.time() if now is None else now
        for d in detections:
            if d.track_id is None:
                continue
            t = self.tracks.get(d.track_id)
            if t is None:
                t = Track(
                    track_id=d.track_id,
                    bbox=d.bbox,
                    first_seen=now,
                    last_seen=now,
                    positions=deque(maxlen=self.max_history),
                )
                self.tracks[d.track_id] = t
                self._next_id = max(self._next_id, d.track_id + 1)
            t.last_seen = now
            t.bbox = d.bbox
            t.positions.append(d.center)
        self.prune(now)
        return self.tracks

    def update_iou(
        self,
        detections: List[Detection],
        now: Optional[float] = None,
        iou_thr: float = 0.3,
    ) -> List[Detection]:
        """Track-by-detection for batched mode (no upstream ByteTrack ids).

        Greedy IoU assignment: each detection inherits the track id of the most-
        overlapping existing track (above ``iou_thr``); unmatched detections get
        a fresh id. Returns the same Detection objects with ``.track_id`` filled
        in, so the rest of the pipeline (visualizer, conditions) treats them
        identically to the ByteTrack path. Simple — not appearance-based — but
        adequate per-camera at the kind of frame rates batched detection runs at.
        """
        now = time.time() if now is None else now
        used: set[int] = set()
        out: List[Detection] = []
        # Score every (det, track) pair, then assign greedily by descending IoU.
        scored: List[Tuple[float, int, int]] = []  # (iou, det_idx, track_id)
        track_items = list(self.tracks.items())
        for di, d in enumerate(detections):
            for tid, t in track_items:
                v = _iou(d.bbox, t.bbox)
                if v >= iou_thr:
                    scored.append((v, di, tid))
        scored.sort(reverse=True)
        det_to_tid: Dict[int, int] = {}
        for _, di, tid in scored:
            if di in det_to_tid or tid in used:
                continue
            det_to_tid[di] = tid
            used.add(tid)
        for di, d in enumerate(detections):
            tid = det_to_tid.get(di)
            if tid is None:
                tid = self._next_id
                self._next_id += 1
                self.tracks[tid] = Track(
                    track_id=tid, bbox=d.bbox, first_seen=now, last_seen=now,
                    positions=deque(maxlen=self.max_history),
                )
            t = self.tracks[tid]
            t.last_seen = now
            t.bbox = d.bbox
            t.positions.append(d.center)
            out.append(Detection(track_id=tid, bbox=d.bbox, conf=d.conf, cls=d.cls))
        self.prune(now)
        return out

    def prune(self, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        stale = [tid for tid, t in self.tracks.items() if now - t.last_seen > self.prune_after]
        for tid in stale:
            del self.tracks[tid]

    @property
    def active_count(self) -> int:
        return len(self.tracks)

    def duration_of(self, track_id: int) -> float:
        t = self.tracks.get(track_id)
        return t.duration if t else 0.0

    def reset(self) -> None:
        self.tracks.clear()
