"""CameraManager + CameraWorker — multi-camera grid with one AI-active camera.

The whole venue shows as a live grid; exactly ONE camera at a time runs the full
AI pipeline (YOLO + pose + predicate evaluation + actions). Heavy models are
loaded once and shared; per-camera state (tracker, anti-false-positive, motion
gate, JPEG buffer, events) lives in each worker.

Streaming is asymmetric to fit a CPU-only box with many cameras:
  - INACTIVE tiles open the light 360p SUB stream in on-demand mode (no grabber),
    decoding only at GRID_TILE_FPS — so ~18 tiles stay affordable;
  - the ACTIVE camera opens the 4K MAIN stream continuously (newest frame) for a
    sharp big view + detection. Switching active reopens that camera on 4K and the
    previous one back on sub; the render loop holds the last frame while the new
    source connects, so there is no black-gap flicker.

Each worker decouples *display* from *detection*: the render loop publishes frames
+ last-known boxes; the detect loop (active only) runs YOLO + pose + predicates.
Render is the sole decoder — detect and the tile counter reuse its last frame.
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
        # cache of YOLO instances by path — lets us hot-swap to a lighter model
        # when a many-camera room is opened, without paying the load cost twice.
        from ultralytics import YOLO as _YOLO  # local import to keep top clean
        self._YOLO = _YOLO
        self._model_cache: Dict[str, object] = {self.detector.model_path: self.detector.model}

    def use_model(self, path: str) -> None:
        """Hot-swap the detector's underlying YOLO weights (cached). No-op when
        already on that model. First load downloads + warms up (5-10s); cached
        loads are instant.
        """
        if path == self.detector.model_path:
            return
        with self.lock:
            model = self._model_cache.get(path)
            if model is None:
                model = self._YOLO(path)
                self._model_cache[path] = model
            self.detector.model = model
            self.detector.model_path = path


class CameraWorker:
    def __init__(self, cam: dict, engine: _Engine, manager: "CameraManager") -> None:
        self.id: str = cam["id"]
        self.name: str = cam["name"]
        self.room: str = cam.get("room", cam["name"])       # UI grouping (one box per room)
        self.sub_url: str = cam["url"]                       # light 360p sub-stream (tiles)
        self.main_url: str = cam.get("main_url", cam["url"])  # 4K main (active big view)
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
        # newest decoded+resized frame, stashed by the render loop so the detect
        # loop and the tile counter never decode a second time (one decoder/camera).
        self._last_frame = None
        # per-tile people count for INACTIVE cameras (active uses tracker.active_count)
        self.tile_persons: Optional[int] = None
        self._last_tile_count = 0.0

    # ── helpers ──────────────────────────────────────────────────────────
    @property
    def is_active(self) -> bool:
        """True if THIS camera's room is the active room being analyzed.

        Room-mode semantics: when the user opens 'Restaurant' all its cameras
        are 'active' — they render at RENDER_FPS, open the 4K main stream, and
        feed detections that the manager's room loop produces. Out of the
        active room: light tile mode (sub-stream, GRID_TILE_FPS, count-only).
        """
        return self.manager.active_room_id == self.room

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
        want, cont = self._desired_source()
        try:
            self._src = VideoSource(want, continuous=cont)
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

    def _desired_source(self):
        """Which stream this worker should be on: 4K-continuous if active, else
        light sub-stream on-demand."""
        if self.is_active:
            return self.main_url, True
        return self.sub_url, False

    def switch_stream(self) -> None:
        """Reopen on the stream that matches the current active/inactive state.

        Off the request path (4K can take ~2s to connect). The render loop keeps
        showing the last frame while the new source warms up — no flicker.
        """
        want, cont = self._desired_source()
        if not self.running or self._cur_url == want:
            return
        try:
            new = VideoSource(want, continuous=cont)
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
                # source still connecting / dropped -> hold the last published JPEG
                # (no black gap on a stream swap) and try again shortly.
                time.sleep(0.03)
                continue
            frame = self._maybe_resize(frame)
            self._last_frame = frame  # detect loop + tile counter reuse this
            self.motion_pct = self.motion.score(frame)  # single writer of the gate
            annotated = self._draw(frame, self.is_active)
            ok, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ok:
                self.latest_jpeg = buf.tobytes()
            dt = time.time() - t0
            inst = 1.0 / dt if dt > 0 else 0.0
            ema = inst if ema is None else 0.9 * ema + 0.1 * inst
            self.fps = round(ema, 1)
            # Active camera renders smooth (RENDER_FPS); inactive tiles render
            # slower (GRID_TILE_FPS) so the grid stays affordable on CPU.
            target = settings.RENDER_FPS if self.is_active else settings.GRID_TILE_FPS
            if target > 0:
                time.sleep(max(0.0, (1.0 / target) - (time.time() - t0)))

    # ── detect loop: only tile counter; real detection runs in the manager ──
    def _detect_loop(self) -> None:
        """Per-camera tile counter — refreshes ``tile_persons`` for inactive cams.

        Real detection (active room) is centralized in
        ``CameraManager._room_detect_loop`` so all room cameras share a single
        batched YOLO call. Inactive cameras periodically run a single-frame
        ``detect()`` (no tracking) when the model lock is free.
        """
        while self.running:
            if not self.is_active:
                self._tile_count_tick()
            time.sleep(0.2)

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
        frame = self._last_frame  # the render loop's last sub-stream frame
        if frame is None:
            return
        if not self.engine.lock.acquire(blocking=False):
            return  # active camera is using the model — try again next tick
        try:
            dets = self.engine.detector.detect(frame)
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
            "id": self.id, "name": self.name, "room": self.room, "active": active,
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
        # active_room_id = which room the user is viewing (drives detection).
        # active_id = which camera within that room is the "editing focus"
        # (used by the conditions / zones panels).
        self.active_room_id: Optional[str] = None
        self.active_id: Optional[str] = None
        self._lock = threading.Lock()
        # centralized room detect loop (batched YOLO over all cameras in the
        # active room). Started/stopped on each set_active_room call.
        self._room_thread: Optional[threading.Thread] = None
        self._room_stop = threading.Event()
        self.room_detect_fps: float = 0.0

    def start(self) -> None:
        # Set the default room BEFORE workers spin up, so each worker reads the
        # right active_room_id when choosing its initial stream (main vs sub).
        # Otherwise some default-room workers would race ahead and open the sub
        # stream by mistake. After that we start workers in parallel (one slow/
        # dead stream can't block startup) and spin up the centralized detect
        # loop directly — bypasses set_active_room's tracker/reload work that
        # is meaningless before workers exist.
        default_room = self._room_of(settings.DEFAULT_ACTIVE)
        if default_room is not None:
            self.active_room_id = default_room
            cams = self.cams_in_room(default_room)
            self.active_id = (
                settings.DEFAULT_ACTIVE
                if settings.DEFAULT_ACTIVE in self.workers
                else (cams[0].id if cams else None)
            )
            # adapt the model to the default room size in the background
            n = len(cams)
            target_model = (
                settings.MODEL_SINGLE if n <= 1
                else settings.MODEL_MULTI if n <= 3
                else settings.MODEL_CROWD
            )
            threading.Thread(
                target=self.engine.use_model, args=(target_model,), daemon=True
            ).start()

        for w in self.workers.values():
            threading.Thread(target=w.start, daemon=True).start()

        if self.active_room_id:
            self._room_thread = threading.Thread(target=self._room_detect_loop, daemon=True)
            self._room_thread.start()

    def stop(self) -> None:
        self._room_stop.set()
        if self._room_thread:
            self._room_thread.join(timeout=2.0)
        for w in self.workers.values():
            w.stop()

    def active(self) -> Optional[CameraWorker]:
        return self.workers.get(self.active_id) if self.active_id else None

    def get(self, cam_id: str) -> Optional[CameraWorker]:
        return self.workers.get(cam_id)

    # ── room helpers ─────────────────────────────────────────────────────
    def _room_of(self, cam_id: Optional[str]) -> Optional[str]:
        if cam_id and cam_id in self.workers:
            return self.workers[cam_id].room
        return None

    def cams_in_room(self, room: Optional[str]) -> List[CameraWorker]:
        if not room:
            return []
        return [self.workers[i] for i in self.order if self.workers[i].room == room]

    def rooms(self) -> List[Dict]:
        """Distinct rooms with their cameras (preserves order)."""
        seen: Dict[str, List[str]] = {}
        order: List[str] = []
        for i in self.order:
            r = self.workers[i].room
            if r not in seen:
                seen[r] = []
                order.append(r)
            seen[r].append(i)
        return [{"id": r, "name": r, "camera_ids": seen[r]} for r in order]

    # ── activation: by camera (legacy) and by room ───────────────────────
    def set_active(self, cam_id: str) -> bool:
        """Legacy single-camera activation: routes to the camera's room."""
        if cam_id not in self.workers:
            return False
        return self.set_active_room(self.workers[cam_id].room, primary_cam=cam_id)

    def set_active_room(self, room: Optional[str], primary_cam: Optional[str] = None) -> bool:
        """Switch the active room: stops the previous room loop, swaps stream
        modes (4K main for new room cams, sub-stream for old), resets trackers,
        and starts a new centralized detect loop on the new room.
        """
        if room is not None and not self.cams_in_room(room):
            return False
        old_cams = self.cams_in_room(self.active_room_id)
        new_cams = self.cams_in_room(room)

        # stop the running room detect loop before we re-point trackers
        self._room_stop.set()
        if self._room_thread and self._room_thread.is_alive():
            self._room_thread.join(timeout=2.0)
        self._room_stop = threading.Event()

        with self._lock:
            # reset state on cameras moving in/out of the active set
            for w in set(old_cams) | set(new_cams):
                w.tracker.reset()
                with w._res_lock:
                    w._last_dets, w._last_pose_map = [], {}
            self.active_room_id = room
            # pick a primary camera within the room (for editing focus)
            if primary_cam and primary_cam in self.workers and self.workers[primary_cam] in new_cams:
                self.active_id = primary_cam
            else:
                self.active_id = new_cams[0].id if new_cams else None
            # condition/zone reload so per-camera rules re-bind correctly
            for w in new_cams:
                w.reload()

        # stream swaps in background (4K connect ~2s; render holds last frame)
        for w in old_cams:
            if w not in new_cams:
                threading.Thread(target=w.switch_stream, daemon=True).start()
        for w in new_cams:
            threading.Thread(target=w.switch_stream, daemon=True).start()

        # adapt the model to the room size (more cams = lighter model so the
        # batched detect stays real-time on CPU). Off the request path — the
        # very first switch to a new model can take 5-10s to load.
        if new_cams:
            n = len(new_cams)
            target_model = (
                settings.MODEL_SINGLE if n <= 1
                else settings.MODEL_MULTI if n <= 3
                else settings.MODEL_CROWD
            )
            threading.Thread(
                target=self.engine.use_model, args=(target_model,), daemon=True
            ).start()

        # spin up a fresh room loop (no-op if room is None)
        if new_cams:
            self._room_thread = threading.Thread(target=self._room_detect_loop, daemon=True)
            self._room_thread.start()
        return True

    # ── room detect loop: batched YOLO over all cameras in active room ───
    def _room_detect_loop(self) -> None:
        """Single shared loop that batched-detects every camera in the active
        room each cycle, then dispatches per-camera tracking + condition eval.

        Costs ~1.5-3x of a single-frame detect for batches up to ~6 frames on
        CPU (Ultralytics batches into one inference pass), so a 4-cam room at
        DETECT_MAX_FPS=2 stays affordable. The lock prevents per-tile counters
        from interleaving while a batch is in flight.
        """
        ema = None
        while not self._room_stop.is_set():
            room_cams = self.cams_in_room(self.active_room_id)
            if not room_cams:
                time.sleep(0.1)
                continue

            target_fps = max(0.5, settings.DETECT_MAX_FPS)
            cycle_t0 = time.time()

            # gather freshest available frame from each room camera
            frames: List = []
            cams: List[CameraWorker] = []
            for w in room_cams:
                f = w._last_frame
                if f is not None:
                    frames.append(f)
                    cams.append(w)
            if not frames:
                time.sleep(0.05)
                continue

            t0 = time.time()
            try:
                with self.engine.lock:
                    batch_dets = self.engine.detector.detect_batch(frames)
            except Exception as e:  # noqa: BLE001
                # one bad frame shouldn't kill the loop
                batch_dets = [[] for _ in frames]
                _ = e

            now = time.time()
            for w, frame, dets in zip(cams, frames, batch_dets):
                tracked = w.tracker.update_iou(dets, now)
                with w._res_lock:
                    w._last_dets = tracked

                with w._cfg_lock:
                    conditions = list(w._conditions)
                    zones = dict(w._zones)

                need_pose = any(
                    c["enabled"] and c["predicate"].evaluator == "pose" for c in conditions
                )
                # pose runs per-camera (small model, only when a pose rule is on)
                poses = self.engine.pose.analyze(frame) if need_pose else []
                pose_map = self.engine.pose.associate(poses, tracked) if need_pose else {}
                with w._res_lock:
                    w._last_pose_map = pose_map

                run_vlm = w.sampler.should_run_vlm(frame, now)
                ctx = EvalContext(
                    frame=frame, detections=tracked, poses=poses, pose_map=pose_map,
                    tracks=w.tracker.tracks, zones=zones, now=now,
                )
                for cond in conditions:
                    if not cond["enabled"]:
                        continue
                    pred: Predicate = cond["predicate"]
                    if pred.evaluator == "vlm" and not run_vlm:
                        continue
                    result = self.engine.evaluator.evaluate(pred, ctx)
                    fired, _ = w.afp.should_fire(pred, result, now)
                    if fired:
                        w._on_fire(cond, result)
                w._last_detect = now
                # per-camera detect_fps mirrors the room rate (shared budget)

            dt = time.time() - t0
            inst = 1.0 / dt if dt > 0 else 0.0
            ema = inst if ema is None else 0.9 * ema + 0.1 * inst
            self.room_detect_fps = round(ema, 1)
            for w in cams:
                w.detect_fps = self.room_detect_fps

            # rate cap: the whole batch is ONE detection cycle for the room
            elapsed = time.time() - cycle_t0
            time.sleep(max(0.0, 1.0 / target_fps - elapsed))

    def cameras_state(self) -> dict:
        return {
            "active": self.active_id,
            "active_room": self.active_room_id,
            "cameras": [self.workers[i].tile_state(self.workers[i].is_active) for i in self.order],
        }

    def rooms_state(self) -> dict:
        """Summary for the landing map: one entry per room with last counts."""
        out = []
        for r in self.rooms():
            cams = self.cams_in_room(r["id"])
            count = 0
            n_known = 0
            for w in cams:
                v = w.tracker.active_count if w.is_active else w.tile_persons
                if v is not None:
                    count += v
                    n_known += 1
            out.append({
                "id": r["id"], "name": r["name"],
                "camera_ids": r["camera_ids"], "n_cameras": len(cams),
                "persons": count if n_known else None,
                "active": r["id"] == self.active_room_id,
            })
        return {"active_room": self.active_room_id, "rooms": out}

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
