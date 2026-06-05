"""CameraManager + CameraWorker — multi-camera grid with one AI-active camera.

The whole venue shows as a live grid; exactly ONE camera at a time runs the full
AI pipeline (YOLO + pose + predicate evaluation + actions). Heavy models are
loaded once and shared; per-camera state (tracker, anti-false-positive, motion
gate, JPEG buffer, events) lives in each worker.

Each worker decouples *display* from *detection*:

  - render loop (~RENDER_FPS): publishes the freshest frame + last-known boxes,
    so the live view stays smooth no matter how slow YOLO is on CPU;
  - detect loop (active camera only): runs YOLO *only when the OpenCV MotionGate
    sees movement*, evaluates each condition, and dispatches actions.

A CPU-only box can't run heavy detection on N cameras at once, so inactive
cameras only decode + draw a light tile (name + motion dot); zero YOLO.
"""
from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from typing import Dict, List, Optional

import cv2

from backend.actions.dispatcher import ActionDispatcher
from backend.antifalse import AntiFalsePositive
from backend.config import settings
from backend.core.detector import PersonDetector
from backend.core.pose_analyzer import PoseAnalyzer
from backend.core.reference_frame import AdaptiveSampler, MotionGate
from backend.core.tracker import TrackManager
from backend.core.video_source import VideoSource
from backend.predicates.evaluator import EvalContext, HybridEvaluator
from backend.predicates.types import Predicate
from backend.vlm.client import OllamaVLMClient

try:
    from backend.visualizer import draw_overlay as _draw_overlay  # full overlay (PAS 12)
except Exception:  # pragma: no cover
    _draw_overlay = None


class _Engine:
    """Heavy models shared by every camera (only the active one ever uses them)."""

    def __init__(self) -> None:
        self.detector = PersonDetector()
        self.pose = PoseAnalyzer()
        self.vlm = OllamaVLMClient()
        self.evaluator = HybridEvaluator(self.pose, self.vlm, vlm_max_fps=settings.VLM_MAX_FPS)
        self.dispatcher = ActionDispatcher()
        # serialize model use so a camera switch can't run two detections at once
        self.lock = threading.Lock()


class CameraWorker:
    def __init__(self, cam: dict, engine: _Engine, manager: "CameraManager") -> None:
        self.id: str = cam["id"]
        self.name: str = cam["name"]
        self.sub_url: str = cam["url"]                       # light sub-stream (tile)
        self.main_url: str = cam.get("main_url", cam["url"])  # 4K main (active)
        self._cur_url: Optional[str] = None
        self.engine = engine
        self.manager = manager

        # per-camera state
        self.tracker = TrackManager()
        self.afp = AntiFalsePositive()
        self.sampler = AdaptiveSampler()                       # gates the VLM
        self.motion = MotionGate(min_changed_pct=settings.MOTION_MIN_PCT)  # gates YOLO
        self.motion_pct = 0.0

        self._conditions: List[dict] = []
        self._zones: Dict[str, list] = {}
        self._cfg_lock = threading.Lock()

        # last detection result the render loop draws (written by the detect loop)
        self._last_dets: list = []
        self._last_pose_map: dict = {}
        self._res_lock = threading.Lock()

        self.latest_jpeg: Optional[bytes] = None
        self.events: deque = deque(maxlen=200)
        self._event_seq = 0
        self.fps = 0.0          # render (display) fps
        self.detect_fps = 0.0   # AI fps
        self.running = False
        self.error: Optional[str] = None
        self._src: Optional[VideoSource] = None
        self._threads: List[threading.Thread] = []
        self._last_detect = 0.0
        # per-tile people count for INACTIVE cameras (active uses tracker.active_count)
        self.tile_persons: Optional[int] = None
        self._last_tile_count = 0.0

    # ── helpers ──────────────────────────────────────────────────────────
    @property
    def is_active(self) -> bool:
        return self.manager.active_id == self.id

    @property
    def vlm(self):  # used by the condition compiler via get_pipeline()
        return self.engine.vlm

    # ── config (per-camera conditions + zones) ───────────────────────────
    def load_config(self) -> None:
        from backend.database import SessionLocal
        from backend.models import Condition, Zone

        conds: List[dict] = []
        zones: Dict[str, list] = {}
        db = SessionLocal()
        try:
            for c in db.query(Condition).all():
                cam = getattr(c, "camera_id", None)
                if cam not in (None, self.id):
                    continue  # belongs to another camera
                try:
                    pred = Predicate(**(c.predicate or {}))
                except Exception:
                    pred = Predicate(type="SEMANTIC", original_text=c.text)
                conds.append({"id": c.id, "text": c.text, "predicate": pred,
                              "action": c.action or {"type": "log"}, "enabled": bool(c.enabled)})
            for z in db.query(Zone).all():
                if getattr(z, "camera_id", None) in (None, self.id):
                    zones[z.name] = z.polygon
        finally:
            db.close()
        with self._cfg_lock:
            self._conditions = conds
            self._zones = zones

    def reload(self) -> None:
        self.load_config()

    # ── lifecycle ────────────────────────────────────────────────────────
    def start(self) -> None:
        if self.running:
            return
        self.running = True
        want = self.main_url if self.is_active else self.sub_url  # active opens 4K
        try:
            self._src = VideoSource(want)
            self._cur_url = want
        except Exception as e:  # noqa: BLE001
            self.error = f"open failed: {e}"
            self.running = False
            return
        self.load_config()
        self._threads = [
            threading.Thread(target=self._render_loop, daemon=True),
            threading.Thread(target=self._detect_loop, daemon=True),
        ]
        for t in self._threads:
            t.start()

    def set_stream(self, main: bool) -> None:
        """Reopen on the 4K main stream (active) or the light sub-stream (tile).

        Runs off the request path (4K can take ~2s to connect); the render/detect
        loops tolerate the brief swap (a read on the released source returns None).
        """
        want = self.main_url if main else self.sub_url
        if self._cur_url == want or not self.running:
            return
        try:
            new = VideoSource(want)
        except Exception as e:  # noqa: BLE001
            self.error = f"open failed: {e}"
            return
        old = self._src
        self._src = new
        self._cur_url = want
        self.error = None
        if old is not None:
            old.release()

    def stop(self) -> None:
        self.running = False
        for t in self._threads:
            t.join(timeout=2.0)
        if self._src is not None:
            self._src.release()

    # ── render loop: smooth display, decoupled from detection ────────────
    def _render_loop(self) -> None:
        ema = None
        while self.running:
            t0 = time.time()
            frame = self._src.read() if self._src else None
            if frame is None:
                time.sleep(0.03)
                continue
            frame = self._maybe_resize(frame)
            self.motion_pct = self.motion.score(frame)  # single writer of the gate
            annotated = self._draw(frame, self.is_active)
            ok, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ok:
                self.latest_jpeg = buf.tobytes()
            dt = time.time() - t0
            inst = 1.0 / dt if dt > 0 else 0.0
            ema = inst if ema is None else 0.9 * ema + 0.1 * inst
            self.fps = round(ema, 1)
            target = settings.RENDER_FPS if self.is_active else settings.GRID_TILE_FPS
            if target > 0:
                time.sleep(max(0.0, (1.0 / target) - (time.time() - t0)))

    # ── detect loop: active camera only, motion-gated ────────────────────
    def _detect_loop(self) -> None:
        ema = None
        while self.running:
            if not self.is_active:
                self._tile_count_tick()   # keep this tile's people counter live
                time.sleep(0.2)
                continue
            now = time.time()
            # rate cap: analyze at most DETECT_MAX_FPS frames/sec (1 = once a second)
            min_interval = 1.0 / settings.DETECT_MAX_FPS if settings.DETECT_MAX_FPS > 0 else 0.0
            since = now - self._last_detect
            if since < min_interval:
                time.sleep(min(0.05, min_interval - since))
                continue

            frame = self._src.read() if self._src else None
            if frame is None:
                time.sleep(0.03)
                continue
            frame = self._maybe_resize(frame)

            moving = self.motion_pct >= settings.MOTION_MIN_PCT
            forced = since >= 5.0  # refresh a fully static scene at least every 5s
            if not (moving or forced):
                time.sleep(0.05)  # OpenCV motion gate: static scene -> skip YOLO
                continue

            t0 = time.time()
            with self.engine.lock:
                if not self.is_active:
                    continue  # lost active while waiting on the lock
                dets = self.engine.detector.detect_and_track(frame)
                self.tracker.update(dets, now)
                with self._cfg_lock:
                    conditions = list(self._conditions)
                    zones = dict(self._zones)
                need_pose = any(
                    c["enabled"] and c["predicate"].evaluator == "pose" for c in conditions
                )
                poses = self.engine.pose.analyze(frame) if need_pose else []
                pose_map = self.engine.pose.associate(poses, dets) if need_pose else {}

            with self._res_lock:
                self._last_dets = dets
                self._last_pose_map = pose_map

            run_vlm = self.sampler.should_run_vlm(frame, now)
            ctx = EvalContext(frame=frame, detections=dets, poses=poses, pose_map=pose_map,
                              tracks=self.tracker.tracks, zones=zones, now=now)
            for cond in conditions:
                if not cond["enabled"]:
                    continue
                pred: Predicate = cond["predicate"]
                if pred.evaluator == "vlm" and not run_vlm:
                    continue
                result = self.engine.evaluator.evaluate(pred, ctx)
                fired, _ = self.afp.should_fire(pred, result, now)
                if fired:
                    self._on_fire(cond, result)

            self._last_detect = now
            dt = time.time() - t0
            inst = 1.0 / dt if dt > 0 else 0.0
            ema = inst if ema is None else 0.9 * ema + 0.1 * inst
            self.detect_fps = round(ema, 1)

    # ── per-tile people count (inactive cameras) ────────────────────────
    def _tile_count_tick(self) -> None:
        """Refresh this (inactive) camera's people count every GRID_COUNT_INTERVAL.

        Counts only when the shared model lock is FREE (non-blocking) so the
        active camera's detection is never delayed. Plain detect (no tracking) —
        a tile counter doesn't need stable ids.
        """
        interval = settings.GRID_COUNT_INTERVAL
        if interval <= 0:
            return
        now = time.time()
        if now - self._last_tile_count < interval:
            return
        frame = self._src.read() if self._src else None
        if frame is None:
            return
        if not self.engine.lock.acquire(blocking=False):
            return  # active camera is using the model — try again next tick
        try:
            dets = self.engine.detector.detect(self._maybe_resize(frame))
        except Exception:
            dets = []
        finally:
            self.engine.lock.release()
        self.tile_persons = len(dets)
        self._last_tile_count = now

    # ── drawing ──────────────────────────────────────────────────────────
    def _maybe_resize(self, frame):
        if settings.FRAME_MAX_WIDTH and frame.shape[1] > settings.FRAME_MAX_WIDTH:
            h, w = frame.shape[:2]
            nh = int(h * settings.FRAME_MAX_WIDTH / w)
            return cv2.resize(frame, (settings.FRAME_MAX_WIDTH, nh))
        return frame

    def _draw(self, frame, active: bool):
        if active and _draw_overlay is not None:
            with self._res_lock:
                dets = list(self._last_dets)
                pose_map = dict(self._last_pose_map)
            return _draw_overlay(frame, dets, pose_map, self.tracker, self._hud_state(), self._zones)
        return self._draw_tile(frame, active)

    def _draw_tile(self, frame, active: bool):
        img = frame.copy()
        h, w = img.shape[:2]
        cv2.rectangle(img, (0, 0), (w, 22), (20, 20, 20), -1)
        cv2.putText(img, self.name, (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0, 255, 170) if active else (210, 210, 210), 1)
        moving = self.motion_pct >= settings.MOTION_MIN_PCT
        cv2.circle(img, (w - 13, 11), 5, (0, 0, 255) if moving else (90, 90, 90), -1)
        return img

    def _hud_state(self) -> dict:
        return {"fps": self.fps, "detect_fps": self.detect_fps,
                "persons": self.tracker.active_count,
                "conditions": len([c for c in self._conditions if c["enabled"]]),
                "last_event": self.events[-1] if self.events else None}

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
            "camera_id": self.id,
            "camera_name": self.name,
        }
        self.events.append(ev)
        self._record_event(cond, result)
        try:
            asyncio.run(self.engine.dispatcher.dispatch(
                cond["action"], {"reason": result.reason, "confidence": result.confidence}))
        except Exception:
            pass

    def _record_event(self, cond: dict, result) -> None:
        from backend.database import SessionLocal
        from backend.models import Event

        db = SessionLocal()
        try:
            db.add(Event(condition_id=cond["id"], detected=True,
                         confidence=float(result.confidence), reason=result.reason,
                         action_taken=cond["action"].get("type", "log"),
                         camera_id=self.id))
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    # ── state surfaces ───────────────────────────────────────────────────
    def state(self) -> dict:
        return {
            "running": self.running, "fps": self.fps,
            "persons": self.tracker.active_count,
            "conditions": len([c for c in self._conditions if c["enabled"]]),
            "error": self.error, "last_event": self.events[-1] if self.events else None,
            "camera_id": self.id, "camera_name": self.name,
            "detect_fps": self.detect_fps, "motion": round(self.motion_pct, 2),
        }

    def tile_state(self, active: bool) -> dict:
        return {
            "id": self.id, "name": self.name, "active": active,
            "fps": self.fps, "detect_fps": self.detect_fps,
            "persons": self.tracker.active_count if active else self.tile_persons,
            "motion": round(self.motion_pct, 2),
            "moving": self.motion_pct >= settings.MOTION_MIN_PCT,
            "error": self.error,
        }

    def events_since(self, seq: int) -> List[dict]:
        return [e for e in list(self.events) if e["seq"] > seq]


class CameraManager:
    def __init__(self) -> None:
        self.engine = _Engine()
        self.workers: Dict[str, CameraWorker] = {}
        self.order: List[str] = []
        for cam in settings.CAMERAS:
            self.workers[cam["id"]] = CameraWorker(cam, self.engine, self)
            self.order.append(cam["id"])
        self.active_id: Optional[str] = (
            settings.DEFAULT_ACTIVE if settings.DEFAULT_ACTIVE in self.workers
            else (self.order[0] if self.order else None)
        )
        self._lock = threading.Lock()

    def start(self) -> None:
        # connect cameras in parallel so one slow/dead stream can't block startup
        for w in self.workers.values():
            threading.Thread(target=w.start, daemon=True).start()

    def stop(self) -> None:
        for w in self.workers.values():
            w.stop()

    def active(self) -> Optional[CameraWorker]:
        return self.workers.get(self.active_id) if self.active_id else None

    def get(self, cam_id: str) -> Optional[CameraWorker]:
        return self.workers.get(cam_id)

    def set_active(self, cam_id: str) -> bool:
        if cam_id not in self.workers:
            return False
        old = self.workers.get(self.active_id) if self.active_id else None
        with self._lock:
            if old is not None and old.id != cam_id:
                old.tracker.reset()
                with old._res_lock:
                    old._last_dets, old._last_pose_map = [], {}
            self.active_id = cam_id
            new = self.workers[cam_id]
            new.tracker.reset()
            with new._res_lock:
                new._last_dets, new._last_pose_map = [], {}
            self.engine.detector.reset_tracker()
            new.reload()
        # swap streams in the background (4K connect can take ~2s): the new active
        # camera upgrades to 4K main; the old one drops back to the light sub-stream.
        threading.Thread(target=new.set_stream, args=(True,), daemon=True).start()
        if old is not None and old.id != cam_id:
            threading.Thread(target=old.set_stream, args=(False,), daemon=True).start()
        return True

    def cameras_state(self) -> dict:
        return {
            "active": self.active_id,
            "cameras": [self.workers[i].tile_state(i == self.active_id) for i in self.order],
        }

    def reload(self, cam_id: Optional[str] = None) -> None:
        if cam_id and cam_id in self.workers:
            self.workers[cam_id].reload()
        else:
            for w in self.workers.values():
                w.reload()


_manager: Optional[CameraManager] = None


def get_manager() -> CameraManager:
    global _manager
    if _manager is None:
        _manager = CameraManager()
    return _manager
