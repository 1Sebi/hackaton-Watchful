"""CameraManager + CameraWorker — one stream per camera, one loop per camera.

Invariants enforced here (do not break in future changes):

  1. EXACTLY ONE stream source per camera. We open the upgraded sub-stream and
     never switch — no main/sub toggle, no per-state stream swap. Reconfigure
     the NVR sub profile (scripts/upgrade_substreams.py) to whatever quality
     detection needs; the app consumes that one feed.

  2. EXACTLY ONE loop per camera. The same loop decodes a frame, runs YOLO,
     tracks, evaluates conditions, draws the overlay, and publishes the JPEG.
     Display and detection are the same operation at the same FPS — the boxes
     the viewer sees are the boxes that just got computed on that frame.

  3. Non-visible cameras that carry rules still run YOLO + rule evaluation, but
     capped at MONITOR_FPS so they don't steal CPU from the visible cameras.
     They do not render or publish JPEGs (nothing is watching them).

  4. Models are shared. ``_Engine`` holds the single YOLO detector / pose model
     / VLM client; the engine lock serializes inference across workers so a
     thread-unsafe ultralytics model never receives concurrent calls.
"""
from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from typing import Dict, List, Optional

import cv2

from backend.actions.dispatcher import ActionDispatcher
from backend.actions.messaging import send_telegram_video
from backend.antifalse import AntiFalsePositive
from backend.config import settings
from backend.core.detector import PersonDetector
from backend.core.pin_tracker import PinSession
from backend.core.pose_analyzer import PoseAnalyzer
from backend.core.reference_frame import AdaptiveSampler, MotionGate
from backend.core.tracker import TrackManager
from backend.core.video_source import VideoSource
from backend.predicates.evaluator import EvalContext, HybridEvaluator
from backend.predicates.types import Predicate
from backend.vlm.client import OllamaVLMClient

try:
    from backend.visualizer import draw_overlay as _draw_overlay
except Exception:  # pragma: no cover
    _draw_overlay = None


class _Engine:
    """Heavy models shared by every camera worker.

    A single YOLO detector + pose + VLM are reused across all workers; ``lock``
    serializes inference so two workers can't enter the model at the same time
    (ultralytics models are not thread-safe).
    """

    def __init__(self) -> None:
        self.detector = PersonDetector()
        self.pose = PoseAnalyzer()
        self.vlm = OllamaVLMClient()
        self.evaluator = HybridEvaluator(self.pose, self.vlm, vlm_max_fps=settings.VLM_MAX_FPS)
        self.dispatcher = ActionDispatcher()
        self.lock = threading.Lock()


class CameraWorker:
    def __init__(self, cam: dict, engine: _Engine, manager: "CameraManager") -> None:
        self.id: str = cam["id"]
        self.name: str = cam["name"]
        self.room: str = cam.get("room", cam["name"])
        # one stream per camera — the (upgraded) sub-stream is the single source
        # of truth for both display and detection.
        self.url: str = cam["url"]
        self.engine = engine
        self.manager = manager

        # per-camera state
        self.tracker = TrackManager()
        self.afp = AntiFalsePositive()
        self.sampler = AdaptiveSampler()                       # gates the VLM
        self.motion = MotionGate(min_changed_pct=settings.MOTION_MIN_PCT)
        self.motion_pct = 0.0

        self._conditions: List[dict] = []
        self._zones: Dict[str, list] = {}
        self._cfg_lock = threading.Lock()

        # last detection snapshot — read by the WS overlay and the pinned-clip
        # recorder; written by THIS worker's loop each cycle.
        self._last_dets: list = []
        self._last_pose_map: dict = {}
        self._last_frame = None
        self._res_lock = threading.Lock()

        self.latest_jpeg: Optional[bytes] = None
        self.events: deque = deque(maxlen=200)
        self._event_seq = 0
        self.fps = 0.0       # detect=render fps (they are the same thing now)
        self.running = False
        self.error: Optional[str] = None
        self._src: Optional[VideoSource] = None
        self._placeholder: Optional[bytes] = None
        self._thread: Optional[threading.Thread] = None

    # ── helpers ──────────────────────────────────────────────────────────
    @property
    def is_active(self) -> bool:
        """True if THIS camera's room is the one the user is viewing."""
        return self.manager.active_room_id == self.room

    @property
    def is_focus(self) -> bool:
        """True if THIS is the single big-view camera within the active room."""
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
                    continue
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

    def _has_conditions(self) -> bool:
        with self._cfg_lock:
            return any(c["enabled"] for c in self._conditions)

    # ── lifecycle ────────────────────────────────────────────────────────
    def start(self) -> None:
        if self.running:
            return
        self.running = True
        try:
            # continuous=False: no background grabber thread; we decode one
            # frame per loop iteration on demand. TCP back-pressure throttles
            # the NVR to our read rate, so an idle camera (no rules, not active)
            # costs ~zero CPU until something starts reading it. A visible camera
            # reads as fast as decode+YOLO allow, which is the FPS the viewer sees.
            self._src = VideoSource(self.url, continuous=False)
        except Exception as e:  # noqa: BLE001
            self.error = f"open failed: {e}"
            self.running = False
            return
        self.load_config()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._src is not None:
            self._src.release()

    def _placeholder_jpeg(self) -> Optional[bytes]:
        if self._placeholder is not None:
            return self._placeholder
        import numpy as _np
        img = _np.full((360, 640, 3), 26, dtype=_np.uint8)
        cv2.putText(img, self.name, (16, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (210, 210, 210), 1)
        cv2.putText(img, "connecting...", (16, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0, 200, 170), 1)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
        self._placeholder = buf.tobytes() if ok else None
        return self._placeholder

    # ── the ONE loop ─────────────────────────────────────────────────────
    def _loop(self) -> None:
        """Single pipeline per camera: decode → detect → track → eval → draw → publish.

        - VISIBLE cameras (active room): full pipeline, every frame. Render and
          detection share the same frame at the same rate — the boxes the viewer
          sees are the ones computed on the frame they're looking at.
        - NON-VISIBLE rule cameras: detect + evaluate only, capped at MONITOR_FPS
          so they don't steal CPU from visible cameras. No render, no JPEG.
        - Everything else: idle.
        """
        ema_fps = None
        last_pub = None
        last_bg = 0.0
        bg_period = 1.0 / max(0.2, settings.MONITOR_FPS)
        while self.running:
            active = self.is_active
            has_rules = self._has_conditions()
            if not active and not has_rules:
                self.fps = 0.0
                last_pub = None
                time.sleep(0.4)
                continue
            if not active:
                # rule camera, off-screen — rate-cap so it doesn't eat the
                # visible cameras' YOLO budget
                now = time.time()
                if now - last_bg < bg_period:
                    time.sleep(0.05)
                    continue
                last_bg = now

            t0 = time.time()
            frame = self._src.read() if self._src else None
            if frame is None:
                if active and self.latest_jpeg is None:
                    ph = self._placeholder_jpeg()
                    if ph is not None:
                        self.latest_jpeg = ph
                time.sleep(0.05)
                continue
            frame = self._maybe_resize(frame)
            self._last_frame = frame
            self.motion_pct = self.motion.score(frame)
            now = time.time()

            # one YOLO pass — engine lock serializes across workers
            try:
                with self.engine.lock:
                    dets = self.engine.detector.detect(frame)
            except Exception:
                dets = []
            tracked = self.tracker.update_iou(dets, now)
            with self._res_lock:
                self._last_dets = tracked

            with self._cfg_lock:
                conditions = [c for c in self._conditions if c["enabled"]]
                zones = dict(self._zones)
            need_pose = any(c["predicate"].evaluator == "pose" for c in conditions)
            poses = self.engine.pose.analyze(frame) if need_pose else []
            pose_map = self.engine.pose.associate(poses, tracked) if need_pose else {}
            with self._res_lock:
                self._last_pose_map = pose_map

            run_vlm = self.sampler.should_run_vlm(frame, now)
            ctx = EvalContext(
                frame=frame, detections=tracked, poses=poses, pose_map=pose_map,
                tracks=self.tracker.tracks, zones=zones, now=now, camera_id=self.id,
            )
            for cond in conditions:
                pred: Predicate = cond["predicate"]
                if pred.evaluator == "vlm" and not run_vlm:
                    continue
                result = self.engine.evaluator.evaluate(pred, ctx)
                fired, _ = self.afp.should_fire(pred, result, now)
                if fired:
                    self._on_fire(cond, result)

            # grow pin clip (no-op unless this camera is pinned)
            self.manager._pin_record(self, frame, tracked, now)

            if active:
                annotated = self._draw(frame, self.is_focus)
                ok, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok:
                    self.latest_jpeg = buf.tobytes()
                # real fps from cycle-to-cycle gap (what the viewer perceives)
                if last_pub is not None:
                    gap = now - last_pub
                    inst = 1.0 / gap if gap > 0 else 0.0
                    ema_fps = inst if ema_fps is None else 0.9 * ema_fps + 0.1 * inst
                    self.fps = round(ema_fps, 1)
                last_pub = now
            # no explicit rate cap on visible cameras: they run as fast as
            # decode + (lock-serialized) YOLO allow, which IS the truthful fps
            # the user wanted ("ce vedem noi la același fps").
            _ = t0  # keep for future cap if a per-camera ceiling is wanted

    # ── drawing ──────────────────────────────────────────────────────────
    def _maybe_resize(self, frame):
        if settings.FRAME_MAX_WIDTH and frame.shape[1] > settings.FRAME_MAX_WIDTH:
            h, w = frame.shape[:2]
            nh = int(h * settings.FRAME_MAX_WIDTH / w)
            return cv2.resize(frame, (settings.FRAME_MAX_WIDTH, nh))
        return frame

    def _draw(self, frame, focus: bool):
        if focus and _draw_overlay is not None:
            with self._res_lock:
                dets = list(self._last_dets)
                pose_map = dict(self._last_pose_map)
            # boxes=False: the live-view frontend draws its own clickable boxes
            # over this JPEG (sourced from the same _last_dets via /track REST),
            # so we publish a clean frame to avoid double-drawing.
            return _draw_overlay(frame, dets, pose_map, self.tracker, self._hud_state(),
                                 self._zones, boxes=False)
        return self._draw_tile(frame, focus)

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
        return {"fps": self.fps, "detect_fps": self.fps,
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
                cond["action"],
                {"reason": result.reason, "confidence": result.confidence,
                 "camera_id": self.id, "camera_name": self.name}))
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
            "detect_fps": self.fps, "motion": round(self.motion_pct, 2),
        }

    def tile_state(self, active: bool) -> dict:
        return {
            "id": self.id, "name": self.name, "room": self.room, "active": active,
            "fps": self.fps, "detect_fps": self.fps,
            # every loop that runs (visible OR background rule cam) updates the
            # tracker, so active_count is the honest live number for any camera
            # the system is actually watching; idle cams report 0.
            "persons": self.tracker.active_count,
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
        self.active_room_id: Optional[str] = None
        self.active_id: Optional[str] = None
        self._lock = threading.Lock()
        # pinned-person clip (one active session at a time)
        self._pin: Optional[PinSession] = None
        self._pin_lock = threading.Lock()

    def start(self) -> None:
        default_room = self._room_of(settings.DEFAULT_ACTIVE)
        if default_room is not None:
            self.active_room_id = default_room
            cams = self.cams_in_room(default_room)
            self.active_id = (
                settings.DEFAULT_ACTIVE
                if settings.DEFAULT_ACTIVE in self.workers
                else (cams[0].id if cams else None)
            )
        # start workers in parallel — a slow/dead stream can't block startup
        for w in self.workers.values():
            threading.Thread(target=w.start, daemon=True).start()

    def stop(self) -> None:
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
        if cam_id not in self.workers:
            return False
        return self.set_active_room(self.workers[cam_id].room, primary_cam=cam_id)

    def set_active_room(self, room: Optional[str], primary_cam: Optional[str] = None) -> bool:
        """Switch which room the user is viewing.

        With one stream per camera there are no source swaps to coordinate —
        every worker keeps reading its own sub-stream. We just point the
        active_room_id / active_id and reset trackers for cameras entering or
        leaving the visible set so their identities don't bleed across rooms.
        """
        if room is not None and not self.cams_in_room(room):
            return False
        old_cams = self.cams_in_room(self.active_room_id)
        new_cams = self.cams_in_room(room)
        with self._lock:
            for w in set(old_cams) | set(new_cams):
                w.tracker.reset()
                with w._res_lock:
                    w._last_dets, w._last_pose_map = [], {}
            self.active_room_id = room
            if primary_cam and primary_cam in self.workers and self.workers[primary_cam] in new_cams:
                self.active_id = primary_cam
            else:
                self.active_id = new_cams[0].id if new_cams else None
            for w in new_cams:
                w.reload()
        return True

    def cameras_state(self) -> dict:
        return {
            "active": self.active_id,
            "active_room": self.active_room_id,
            "cameras": [self.workers[i].tile_state(self.workers[i].is_active) for i in self.order],
        }

    def rooms_state(self) -> dict:
        out = []
        for r in self.rooms():
            cams = self.cams_in_room(r["id"])
            count = sum(w.tracker.active_count for w in cams)
            out.append({
                "id": r["id"], "name": r["name"],
                "camera_ids": r["camera_ids"], "n_cameras": len(cams),
                "persons": count,
                "active": r["id"] == self.active_room_id,
            })
        return {"active_room": self.active_room_id, "rooms": out}

    def reload(self, cam_id: Optional[str] = None) -> None:
        if cam_id and cam_id in self.workers:
            self.workers[cam_id].reload()
        else:
            for w in self.workers.values():
                w.reload()

    # ── pinned-person tracking ───────────────────────────────────────────
    def detections_for(self, camera_id: Optional[str] = None) -> dict:
        cam_id = camera_id or self.active_id
        w = self.workers.get(cam_id) if cam_id else None
        if w is None:
            return {"camera_id": cam_id, "frame_w": 0, "frame_h": 0, "pinned_id": None, "tracks": []}
        with w._res_lock:
            dets = list(w._last_dets)
            frame = w._last_frame
        fh, fw = (int(frame.shape[0]), int(frame.shape[1])) if frame is not None else (0, 0)
        tracks = []
        for d in dets:
            if d.track_id is None:
                continue
            t = w.tracker.tracks.get(d.track_id)
            x1, y1, x2, y2 = d.bbox
            tracks.append({
                "id": int(d.track_id),
                "bbox": [int(x1), int(y1), int(x2), int(y2)],
                "center": [int((x1 + x2) // 2), int((y1 + y2) // 2)],
                "dur": round(t.duration, 1) if t else 0.0,
            })
        with self._pin_lock:
            pinned = self._pin.track_id if (self._pin and self._pin.camera_id == cam_id) else None
        return {"camera_id": cam_id, "frame_w": fw, "frame_h": fh,
                "pinned_id": pinned, "tracks": tracks}

    def pin_start(self, camera_id: str, track_id: int) -> dict:
        w = self.workers.get(camera_id)
        if w is None:
            return {"ok": False, "error": "unknown camera"}
        with self._pin_lock:
            if self._pin is not None:
                with self._pin.lock:
                    self._pin.finalize()
            self._pin = PinSession(camera_id, w.name, int(track_id))
            status = self._pin.status()
        return {"ok": True, **status}

    def pin_status(self) -> dict:
        with self._pin_lock:
            p = self._pin
        return p.status() if p else {"pinned": False}

    def pin_stop(self) -> dict:
        with self._pin_lock:
            p = self._pin
            self._pin = None
        if p is None:
            return {"ok": False, "error": "nothing pinned"}
        with p.lock:
            info = p.finalize()
        if not info["ok"]:
            return {"ok": False, "error": "no frames recorded (person was not seen)", **info}
        caption = (f"Watchful — tracked person #{info['track_id']} on "
                   f"{info['camera_name']} · {info['duration']}s, {info['frames']} frames")
        tg = send_telegram_video(info["path"], caption)
        return {"ok": tg.get("ok", False), "telegram": tg, **info}

    def _pin_record(self, worker: "CameraWorker", frame, dets: list, now: float) -> None:
        with self._pin_lock:
            p = self._pin
        if p is None or p.camera_id != worker.id:
            return
        det = next((d for d in dets if d.track_id == p.track_id), None)
        if det is None:
            return
        track = worker.tracker.tracks.get(p.track_id)
        try:
            with p.lock:
                with self._pin_lock:
                    active = self._pin is p
                if active:
                    p.record(frame, det, track, now)
        except Exception:  # noqa: BLE001
            pass


_manager: Optional[CameraManager] = None


def get_manager() -> CameraManager:
    global _manager
    if _manager is None:
        _manager = CameraManager()
    return _manager
