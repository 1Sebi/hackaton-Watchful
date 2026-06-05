"""Watchful backend — local, zero-cloud camera AI agent."""
import os as _os

# RTSP hardening — MUST run before ANY cv2/FFmpeg import in the package
# (ultralytics imports cv2 early, so setting these inside video_source.py is too
# late for the log level). Force TCP transport + an 8s timeout, and silence the
# HEVC decoder's "PPS id out of range" / "POC" chatter on noisy sub-streams.
_os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;8000000"
)
_os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "-8")  # AV_LOG_QUIET
