"""Multi-camera people counting via ground-plane homography fusion.

For rooms covered by 2+ overlapping cameras, each camera is mapped to a common
floor plane. A detection's FEET (bottom-center of its bbox) project to a floor
(X, Y); detections from different cameras that land within `merge_dist` of each
other are the SAME person -> counted once.

Calibration per camera = 4+ correspondences (image px -> floor coords in a unit
shared by all cameras of the room, e.g. metres). In production these come from a
UI where the operator clicks floor points; here they live in config.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class CameraFloorMap:
    """Maps one camera's image pixels to the shared floor plane."""
    name: str
    H: np.ndarray  # 3x3 image->floor homography

    @classmethod
    def from_points(cls, name, img_pts, floor_pts) -> "CameraFloorMap":
        import cv2
        img = np.asarray(img_pts, dtype=np.float32)
        flo = np.asarray(floor_pts, dtype=np.float32)
        if len(img) == 4:
            H = cv2.getPerspectiveTransform(img, flo)
        else:
            H, _ = cv2.findHomography(img, flo, cv2.RANSAC)
        return cls(name=name, H=H)

    def reproj_error(self, img_pts, floor_pts) -> float:
        """Mean distance (floor units) between projected img pts and the target."""
        proj = self.to_floor_pts(img_pts)
        flo = np.asarray(floor_pts, dtype=np.float32)
        return float(np.mean(np.linalg.norm(proj - flo, axis=1)))

    def to_floor_pts(self, img_pts) -> np.ndarray:
        import cv2
        pts = np.asarray(img_pts, dtype=np.float32).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(pts, self.H).reshape(-1, 2)

    @staticmethod
    def feet(box) -> tuple[float, float]:
        x1, y1, x2, y2 = box
        return ((x1 + x2) / 2.0, y2)  # bottom-center = where the person stands

    def boxes_to_floor(self, boxes) -> np.ndarray:
        if not len(boxes):
            return np.empty((0, 2), dtype=np.float32)
        return self.to_floor_pts([self.feet(b) for b in boxes])


class RoomCounter:
    """Fuse detections from several cameras of one room into a deduped count."""

    def __init__(self, cams: list[CameraFloorMap], merge_dist: float = 0.7):
        self.cams = {c.name: c for c in cams}
        self.merge_dist = merge_dist  # floor units (e.g. metres)

    def fuse(self, boxes_by_cam: dict[str, list]) -> dict:
        """boxes_by_cam: {cam_name: [bbox,...]} -> deduped floor points + count."""
        pts = []
        for name, boxes in boxes_by_cam.items():
            cam = self.cams.get(name)
            if cam is None:
                continue
            for fp in cam.boxes_to_floor(boxes):
                pts.append(fp)

        merged: list[np.ndarray] = []
        for p in pts:
            if all(np.linalg.norm(p - q) > self.merge_dist for q in merged):
                merged.append(p)

        naive = sum(len(b) for b in boxes_by_cam.values())
        return {
            "count": len(merged),          # deduped (the real number)
            "naive_sum": naive,            # what you'd get without fusion
            "merged_from": naive - len(merged),  # duplicates removed
            "floor_points": [tuple(map(float, p)) for p in merged],
        }
