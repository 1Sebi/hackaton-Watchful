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


class TrackManager:
    def __init__(self, max_history: int = 64, prune_after: float = 2.0) -> None:
        self.tracks: Dict[int, Track] = {}
        self.max_history = max_history
        self.prune_after = prune_after  # seconds since last_seen before forgetting

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
            t.last_seen = now
            t.bbox = d.bbox
            t.positions.append(d.center)
        self.prune(now)
        return self.tracks

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
