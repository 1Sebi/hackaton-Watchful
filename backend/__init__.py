"""Watchful backend — local, zero-cloud camera AI agent."""
import os as _os

# RTSP hardening — MUST run before ANY cv2/FFmpeg import in the package
# (ultralytics imports cv2 early, so setting these inside video_source.py is too
# late). Force TCP transport; stimeout 5s so a stalled stream errors out fast;
# fflags;discardcorrupt makes FFmpeg DROP corrupt/partial frames instead of
# painting the grey blocky smear ("purici") from a keyframe-less P-frame decode.
_os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|stimeout;5000000|fflags;discardcorrupt",
)
_os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "-8")  # AV_LOG_QUIET
