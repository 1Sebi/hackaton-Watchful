"""VideoSource — unified frame capture for webcam, RTSP, or video file.

Buffered at size 1 so ``read()`` always returns the freshest frame (no stale
queue), with bounded auto-reconnect for flaky RTSP streams. Usable as a context
manager. This is the single perception entry point for the whole agent loop.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from typing import Optional, Union

# Harden RTSP transport: force TCP (not lossy UDP) + an 8s open/read timeout.
# Must be set BEFORE cv2 is imported so FFmpeg picks it up — prevents UDP
# artifacts ("PPS id out of range" on some HEVC cams) and infinite hangs on a
# dead stream. (Validated against the live ThePlace NVRs.)
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    # tcp = no lossy UDP; stimeout 5s = socket I/O timeout so a silently stalled
    # stream errors out (and we reconnect) instead of hanging read() forever;
    # fflags;discardcorrupt = FFmpeg DROPS corrupt/partial frames instead of
    # emitting the grey blocky smear ("purici") when it decodes a P-frame without
    # its keyframe (the "PPS id out of range / Could not find ref" cases).
    "rtsp_transport;tcp|stimeout;5000000|fflags;discardcorrupt",
)
# Quiet FFmpeg's HEVC decoder chatter ("PPS id out of range", "Could not find ref
# with POC") — harmless startup/keyframe warnings on some sub-streams; the agent
# loop tolerates them. fatal-only so genuine failures still surface.
os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "8")

import cv2  # noqa: E402
import numpy as np  # noqa: E402


class VideoSource:
    """Wrap ``cv2.VideoCapture`` with a tiny buffer + reconnect logic.

    ``source`` may be:
      * ``int``  -> webcam index (e.g. ``0``)
      * ``str``  -> RTSP URL (``rtsp://...``) or a path to a video file
    """

    def __init__(
        self,
        source: Union[int, str] = 0,
        max_reconnect: int = 60,   # keep retrying a flaky focus stream (resets on success)
        reconnect_delay: float = 1.0,
        continuous: bool = True,
        stall_timeout: float = 6.0,  # no fresh frame for this long -> force reopen
    ) -> None:
        self.source = self._coerce(source)
        self.max_reconnect = max_reconnect
        self.reconnect_delay = reconnect_delay
        # continuous=True: a background grabber decodes at full stream rate and keeps
        #   the newest frame (low latency — for the AI-active 4K camera).
        # continuous=False: NO grabber; read() decodes one frame on demand, so an
        #   inactive grid tile read at ~3 fps decodes ~3 fps (not ~24) — the lever
        #   that makes ~18 simultaneous sub-streams affordable on CPU.
        self.continuous = continuous
        self.stall_timeout = stall_timeout
        self._cap: Optional[cv2.VideoCapture] = None
        self._reconnects = 0
        self._latest: Optional[np.ndarray] = None
        self._last_frame_ts = time.time()  # for the stall watchdog
        self._frame_lock = threading.Lock()
        self._read_lock = threading.Lock()  # serialize on-demand cap.read()
        self._grab_thread: Optional[threading.Thread] = None
        self._watchdog_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.open()
        if self.continuous and not self.is_file:
            self._grab_thread = threading.Thread(target=self._grab_loop, daemon=True)
            self._grab_thread.start()
            # watchdog: a TCP stream can connect then silently stop sending data;
            # cap.read() then blocks past stimeout on some builds. The watchdog
            # force-releases the cap so the grabber errors out and reopens, instead
            # of the feed freezing on the last frame forever.
            self._watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
            self._watchdog_thread.start()

    # ── helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _coerce(source: Union[int, str]) -> Union[int, str]:
        # "0" -> 0 (webcam index); keep rtsp:// URLs and file paths as str
        if isinstance(source, str) and source.isdigit():
            return int(source)
        return source

    @property
    def is_rtsp(self) -> bool:
        return isinstance(self.source, str) and self.source.lower().startswith("rtsp")

    @property
    def is_file(self) -> bool:
        return isinstance(self.source, str) and not self.is_rtsp

    def _backend(self) -> int:
        if isinstance(self.source, int):
            # Media Foundation delivers full 30 FPS @ 640x480 on Windows webcams;
            # DirectShow's auto-exposure caps delivery to ~10 FPS in indoor light.
            return cv2.CAP_MSMF if sys.platform == "win32" else cv2.CAP_ANY
        if self.is_rtsp:
            return cv2.CAP_FFMPEG  # RTSP over FFmpeg
        return cv2.CAP_ANY

    # ── lifecycle ────────────────────────────────────────────────────────
    def open(self) -> None:
        if self._cap is not None:
            self._cap.release()
        self._cap = cv2.VideoCapture(self.source, self._backend())
        if isinstance(self.source, int):
            # Webcams via DirectShow default to uncompressed YUY2 (~10 FPS @ 640x480).
            # Requesting MJPG unlocks the camera's high-FPS compressed mode.
            try:
                self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                self._cap.set(cv2.CAP_PROP_FPS, 30)
            except Exception:
                pass
        # tiny buffer -> read() yields the freshest frame, not a queued stale one
        try:
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        if not self._cap.isOpened():
            raise RuntimeError(f"VideoSource: could not open source {self.source!r}")
        if self.is_rtsp:
            # the first frames are gray/partial until the decoder hits a keyframe;
            # discard a few so a (re)connect never paints a half-decoded GOP.
            for _ in range(8):
                self._cap.read()
        self._last_frame_ts = time.time()

    def release(self) -> None:
        self._stop.set()
        for t in (self._grab_thread, self._watchdog_thread):
            if t is not None and t.is_alive():
                t.join(timeout=2.0)
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    # ── properties ───────────────────────────────────────────────────────
    @property
    def width(self) -> int:
        return int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if self._cap else 0

    @property
    def height(self) -> int:
        return int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if self._cap else 0

    @property
    def fps(self) -> float:
        fps = self._cap.get(cv2.CAP_PROP_FPS) if self._cap else 0.0
        # webcams/files sometimes report 0 or garbage -> normalise to 0.0
        return float(fps) if fps and fps > 0 else 0.0

    # ── frame access ─────────────────────────────────────────────────────
    def read(self) -> Optional[np.ndarray]:
        """Return the freshest BGR frame, or ``None`` if not ready/exhausted.

        Files are read on demand (preserves pacing + EOF). Live sources hand
        back whatever the background grabber last captured — never a stale
        queued frame — so the consumer always sees *now*.
        """
        if self.is_file:
            if self._cap is None:
                return None
            ok, frame = self._cap.read()
            return frame if ok and frame is not None else None
        if self.continuous:
            with self._frame_lock:
                return self._latest
        # on-demand (tile) mode: decode one frame now. TCP back-pressure keeps the
        # decode near the read rate, so a tile read at GRID_TILE_FPS costs ~that.
        with self._read_lock:
            if self._cap is None:
                return None
            try:
                ok, frame = self._cap.read()
            except Exception:
                ok, frame = False, None
            if ok and frame is not None:
                self._reconnects = 0
                return frame
            return self._reopen_once()

    def _grab_loop(self) -> None:
        """Continuously drain the capture, keeping only the newest frame."""
        while not self._stop.is_set():
            cap = self._cap
            if cap is None:
                if not self._try_reopen():
                    break
                continue
            ok, frame = cap.read()
            if ok and frame is not None:
                self._reconnects = 0
                self._last_frame_ts = time.time()
                with self._frame_lock:
                    self._latest = frame
                continue
            # transient failure (RTSP drop) -> bounded reconnect
            if not self._try_reopen():
                break

    def _watchdog_loop(self) -> None:
        """Force-reopen a silently stalled continuous stream so the feed can't freeze."""
        while not self._stop.is_set():
            if self._stop.wait(2.0):
                return
            if time.time() - self._last_frame_ts <= self.stall_timeout:
                continue
            cap = self._cap  # snapshot — releasing unblocks the grabber's cap.read()
            try:
                if cap is not None:
                    cap.release()
            except Exception:  # noqa: BLE001
                pass
            # debounce so we don't release every 2s while the grabber reopens
            self._last_frame_ts = time.time()

    def _reopen_once(self) -> Optional[np.ndarray]:
        """On-demand (non-continuous) reconnect: try to reopen + grab one frame."""
        if self._reconnects >= self.max_reconnect:
            return None
        self._reconnects += 1
        try:
            self.open()
            ok, frame = self._cap.read()
            return frame if ok and frame is not None else None
        except (RuntimeError, Exception):  # noqa: BLE001
            return None

    def _try_reopen(self) -> bool:
        """Bounded reconnect for a dropped live stream. ``False`` when exhausted."""
        while self._reconnects < self.max_reconnect and not self._stop.is_set():
            self._reconnects += 1
            if self._stop.wait(self.reconnect_delay):
                return False  # released mid-wait
            try:
                self.open()
                return True
            except RuntimeError:
                continue
        return False

    # ── context manager ──────────────────────────────────────────────────
    def __enter__(self) -> "VideoSource":
        return self

    def __exit__(self, *exc) -> None:
        self.release()

    def __repr__(self) -> str:
        return (
            f"VideoSource(source={self.source!r}, "
            f"{self.width}x{self.height}@{self.fps:.0f}fps)"
        )
