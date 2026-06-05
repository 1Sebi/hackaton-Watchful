"""AgentPipeline — the continuous perceive -> reason -> AFP -> act loop.

Runs in a background thread: reads frames, detects+tracks people, estimates pose,
evaluates every enabled condition's predicate (YOLO/Pose/VLM, VLM adaptively
sampled), passes survivors through the anti-false-positive layer, and dispatches
actions on a confirmed trigger. Publishes an annotated JPEG (for MJPEG), a live
state dict, and an event stream (for WebSockets).
"""
from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from typing import Dict, List, Optional

import cv2
import numpy as np

from backend.actions.dispatcher import ActionDispatcher
from backend.antifalse import AntiFalsePositive
from backend.config import settings
from backend.core.detector import PersonDetector
from backend.core.pose_analyzer import PoseAnalyzer
from backend.core.reference_frame import AdaptiveSampler
from backend.core.tracker import TrackManager
from backend.core.video_source import VideoSource
from backend.predicates.evaluator import EvalContext, HybridEvaluator
from backend.predicates.types import Predicate
from backend.vlm.client import OllamaVLMClient

try:
    from backend.visualizer import draw_overlay as _draw_overlay  # full version (PAS 12)
except Exception:  # pragma: no cover - fallback until visualizer exists
    _draw_overlay = None


class AgentPipeline:
    def __init__(self) -> None:
        self.detector = PersonDetector()
        self.pose = PoseAnalyzer()
        self.tracker = TrackManager()
        self.vlm = OllamaVLMClient()
        self.evaluator = HybridEvaluator(self.pose, self.vlm, vlm_max_fps=settings.VLM_MAX_FPS)
        self.afp = AntiFalsePositive()
        self.sampler = AdaptiveSampler()
        self.dispatcher = ActionDispatcher()

        self._conditions: List[dict] = []     # {id, text, predicate: Predicate, action, enabled}
        self._zones: Dict[str, list] = {}
        self._lock = threading.Lock()

        self.latest_jpeg: Optional[bytes] = None
        self.events: deque = deque(maxlen=200)
        self._event_seq = 0
        self.fps = 0.0
        self.running = False
        self.error: Optional[str] = None
        self._thread: Optional[threading.Thread] = None

    # ── config from DB ───────────────────────────────────────────────────
    def load_conditions(self) -> None:
        from backend.database import SessionLocal
        from backend.models import Condition

        conds = []
        db = SessionLocal()
        try:
            for c in db.query(Condition).all():
                try:
                    pred = Predicate(**(c.predicate or {}))
                except Exception:
                    pred = Predicate(type="SEMANTIC", original_text=c.text)
                conds.append({"id": c.id, "text": c.text, "predicate": pred,
                              "action": c.action or {"type": "log"}, "enabled": bool(c.enabled)})
        finally:
            db.close()
        with self._lock:
            self._conditions = conds

    def load_zones(self) -> None:
        from backend.database import SessionLocal
        from backend.models import Zone

        zones = {}
        db = SessionLocal()
        try:
            for z in db.query(Zone).all():
                zones[z.name] = z.polygon
        finally:
            db.close()
        with self._lock:
            self._zones = zones

    def reload(self) -> None:
        self.load_conditions()
        self.load_zones()

    # ── lifecycle ────────────────────────────────────────────────────────
    def start(self) -> None:
        if self.running:
            return
        self.reload()
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.running = False
        if self._thread:
            self._thread.join(timeout=3.0)

    # ── main loop ────────────────────────────────────────────────────────
    def _run(self) -> None:
        try:
            cam = VideoSource(settings.VIDEO_SOURCE)
        except Exception as e:  # noqa: BLE001
            self.error = f"camera open failed: {e}"
            self.running = False
            return

        ema = None
        try:
            while self.running:
                t0 = time.time()
                frame = cam.read()
                if frame is None:
                    time.sleep(0.05)
                    continue
                if settings.FRAME_MAX_WIDTH and frame.shape[1] > settings.FRAME_MAX_WIDTH:
                    h, w = frame.shape[:2]
                    nh = int(h * settings.FRAME_MAX_WIDTH / w)
                    frame = cv2.resize(frame, (settings.FRAME_MAX_WIDTH, nh))
                now = time.time()

                dets = self.detector.detect_and_track(frame)
                self.tracker.update(dets, now)

                with self._lock:
                    zones = dict(self._zones)
                    conditions = list(self._conditions)

                # Pose estimation is a second YOLO pass — only pay for it when a
                # pose predicate (e.g. hand-raise) is actually enabled. A pure
                # "count people" demo then leaves the whole CPU to the detector.
                need_pose = any(
                    c["enabled"] and c["predicate"].evaluator == "pose" for c in conditions
                )
                poses = self.pose.analyze(frame) if need_pose else []
                pose_map = self.pose.associate(poses, dets) if need_pose else {}
                run_vlm = self.sampler.should_run_vlm(frame, now)

                ctx = EvalContext(frame=frame, detections=dets, poses=poses,
                                  pose_map=pose_map, tracks=self.tracker.tracks,
                                  zones=zones, now=now)

                for cond in conditions:
                    if not cond["enabled"]:
                        continue
                    pred: Predicate = cond["predicate"]
                    if pred.evaluator == "vlm" and not run_vlm:
                        continue  # reference-frame gate: skip semantic on static scene
                    result = self.evaluator.evaluate(pred, ctx)
                    fired, reason = self.afp.should_fire(pred, result, now)
                    if fired:
                        self._on_fire(cond, result)

                annotated = self._draw(frame, dets, pose_map)
                ok, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok:
                    self.latest_jpeg = buf.tobytes()

                dt = time.time() - t0
                inst = 1.0 / dt if dt > 0 else 0.0
                ema = inst if ema is None else 0.9 * ema + 0.1 * inst
                self.fps = round(ema, 1)
        finally:
            cam.release()

    # ── event / action on a confirmed trigger ────────────────────────────
    def _on_fire(self, cond: dict, result) -> None:
        self._event_seq += 1
        ev = {
            "seq": self._event_seq,
            "condition_id": cond["id"],
            "text": cond["text"],
            "reason": result.reason,
            "confidence": round(float(result.confidence), 3),
            "evaluator": result.evaluator,
            "ts": time.time(),
            "action": cond["action"].get("type", "log"),
        }
        self.events.append(ev)
        self._record_event(cond, result)
        try:
            asyncio.run(self.dispatcher.dispatch(cond["action"], {"reason": result.reason,
                                                                  "confidence": result.confidence}))
        except Exception:
            pass

    def _record_event(self, cond: dict, result) -> None:
        from backend.database import SessionLocal
        from backend.models import Event

        db = SessionLocal()
        try:
            db.add(Event(condition_id=cond["id"], detected=True,
                         confidence=float(result.confidence), reason=result.reason,
                         action_taken=cond["action"].get("type", "log")))
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    # ── state + overlay ──────────────────────────────────────────────────
    def state(self) -> dict:
        with self._lock:
            n_cond = len([c for c in self._conditions if c["enabled"]])
        return {
            "running": self.running,
            "fps": self.fps,
            "persons": self.tracker.active_count,
            "conditions": n_cond,
            "error": self.error,
            "last_event": self.events[-1] if self.events else None,
        }

    def events_since(self, seq: int) -> List[dict]:
        return [e for e in list(self.events) if e["seq"] > seq]

    def _draw(self, frame, dets, pose_map):
        if _draw_overlay is not None:
            return _draw_overlay(frame, dets, pose_map, self.tracker, self.state(), self._zones)
        # fallback overlay (replaced by backend/visualizer.py in PAS 12)
        img = frame.copy()
        palette = [(0, 255, 0), (255, 128, 0), (0, 128, 255), (255, 0, 255), (0, 255, 255)]
        for d in dets:
            x1, y1, x2, y2 = d.bbox
            color = palette[(d.track_id or 0) % len(palette)]
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
            dur = self.tracker.duration_of(d.track_id) if d.track_id else 0.0
            cv2.putText(img, f"#{d.track_id} {dur:.0f}s", (x1, max(12, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
        cv2.rectangle(img, (0, 0), (img.shape[1], 26), (0, 0, 0), -1)
        cv2.putText(img, f"Watchful  {self.fps:.0f} FPS  persons:{self.tracker.active_count}",
                    (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        return img


_pipeline: Optional[AgentPipeline] = None


def get_pipeline() -> AgentPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = AgentPipeline()
    return _pipeline
