"""Audit each camera's Hikvision SUB stream — the single source of truth.

Per camera in backend/cameras.json this:
  1. GETs /ISAPI/Streaming/channels/<sub_channel_id> via Hikvision ISAPI and
     scrapes resolution / fps / bitrate / codec.
  2. With --probe, also opens the sub RTSP URL and measures real decoded
     resolution + FPS (this is what the app actually consumes).

We audit ONLY the sub-stream because the app uses only the sub-stream — one
stream per camera, no main/sub toggling. Reconfigure the sub profile via
upgrade_substreams.py if detection quality isn't good enough.

Usage:
  python scripts/audit_streams.py               # ISAPI only, fast
  python scripts/audit_streams.py --probe       # also open RTSP and measure
  python scripts/audit_streams.py --probe --only jacuzzi,event_hall
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

import requests
from requests.auth import HTTPDigestAuth


def _nvr_creds(tag: str):
    return (
        os.environ.get(f"{tag}_IP", ""),
        os.environ.get(f"{tag}_USER", "admin"),
        os.environ.get(f"{tag}_PASS", ""),
    )


def _scrape(xml: str, tag: str) -> str:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", xml)
    return m.group(1) if m else ""


def _parse_profile(xml: str) -> dict:
    w = _scrape(xml, "videoResolutionWidth")
    h = _scrape(xml, "videoResolutionHeight")
    fps_raw = _scrape(xml, "maxFrameRate")
    fps = int(fps_raw) / 100 if fps_raw.isdigit() else None
    codec = _scrape(xml, "videoCodecType")
    qctrl = _scrape(xml, "videoQualityControlType")
    cbr = _scrape(xml, "constantBitRate")
    vbr_up = _scrape(xml, "vbrUpperCap")
    bitrate = cbr or vbr_up
    return {
        "w": int(w) if w.isdigit() else None,
        "h": int(h) if h.isdigit() else None,
        "fps": fps,
        "codec": codec,
        "qctrl": qctrl,
        "bitrate_kbps": int(bitrate) if bitrate.isdigit() else None,
    }


def _isapi_get_channel(ip: str, user: str, pw: str, channel_id: int, timeout: float = 6.0):
    url = f"http://{ip}/ISAPI/Streaming/channels/{channel_id}"
    try:
        r = requests.get(url, auth=HTTPDigestAuth(user, pw), timeout=timeout)
    except requests.RequestException as e:
        return {"error": f"net: {e}"}
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}"}
    return _parse_profile(r.text)


def _probe_rtsp(url: str, frames: int = 30) -> dict:
    try:
        from backend.core.video_source import VideoSource
    except Exception as e:
        return {"error": f"import: {e}"}
    try:
        with VideoSource(url) as cam:
            for _ in range(5):
                cam.read()  # warm up
            t0 = time.time()
            n = 0
            for _ in range(frames):
                f = cam.read()
                if f is None:
                    break
                n += 1
            dt = time.time() - t0
            return {
                "real_w": cam.width,
                "real_h": cam.height,
                "real_fps": round(n / dt, 1) if dt > 0 else 0.0,
                "frames": f"{n}/{frames}",
            }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:80]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true",
                    help="open the sub RTSP and measure real decoded resolution + fps")
    ap.add_argument("--only", help="comma-separated camera ids to include")
    ap.add_argument("--cameras", default="backend/cameras.json")
    args = ap.parse_args()

    spec = json.loads(Path(args.cameras).read_text(encoding="utf-8"))
    cams = spec.get("cameras", [])
    if args.only:
        wanted = {x.strip() for x in args.only.split(",")}
        cams = [c for c in cams if c["id"] in wanted]

    header = f"{'id':<14} {'nvr':<5} {'ch':<5} {'sub: codec  res        fps  bitrate':<40}"
    if args.probe:
        header += "  probed"
    print(header)
    print("-" * (110 if args.probe else 70))

    summary = []
    for c in cams:
        tag = str(c.get("nvr", ""))
        ip, user, pw = _nvr_creds(tag)
        if not ip or not pw:
            print(f"{c['id']:<14} {tag:<5}  -- NO CREDS in .env --")
            continue
        sub_ch = int(c["channel"])

        sub_info = _isapi_get_channel(ip, user, pw, sub_ch)

        if "error" in sub_info:
            row = f"{c['id']:<14} {tag:<5} {sub_ch:<5} ERR {sub_info['error'][:60]}"
        else:
            res = f"{sub_info.get('w') or '?'}x{sub_info.get('h') or '?'}"
            br = sub_info.get("bitrate_kbps")
            br_s = f"{br}kb" if br else "?kb"
            sub_fmt = (f"{(sub_info.get('codec') or '?'):<6} {res:<10} "
                       f"{str(sub_info.get('fps') or '?'):<4} {br_s:<8}")
            row = f"{c['id']:<14} {tag:<5} {sub_ch:<5} {sub_fmt:<40}"

        probe = None
        if args.probe and "error" not in sub_info:
            from urllib.parse import quote
            url = f"rtsp://{user}:{quote(pw, safe='')}@{ip}:554/Streaming/Channels/{sub_ch}"
            probe = _probe_rtsp(url)
            if "error" in probe:
                row += f"  ERR {probe['error'][:20]}"
            else:
                row += (f"  {probe['real_w']}x{probe['real_h']} @ "
                        f"{probe['real_fps']}fps ({probe['frames']})")

        print(row)
        summary.append({"id": c["id"], "nvr": tag, "channel": sub_ch,
                        "sub": sub_info, "probed": probe})

    out = Path("eval/stream_audit.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2))
    print()
    print(f"full audit JSON -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
