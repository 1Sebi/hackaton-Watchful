"""Reconfigure each Hikvision camera's SUB-stream to detection-grade settings.

Default target: 1280x720, 15 fps, H.264, VBR with 2 Mbps cap (good recall on
yolov8m@imgsz=640, ~8x cheaper to decode than 4K).

Workflow per channel:
  1. GET  /ISAPI/Streaming/channels/<sub_channel_id>  -> current XML
  2. Patch resolution / fps / codec / bitrate in-place (regex on tags so we
     don't accidentally drop fields we don't know about)
  3. PUT  the modified XML back
  4. GET  again and verify

Usage:
  python scripts/upgrade_substreams.py --dry-run              # show diff only
  python scripts/upgrade_substreams.py                        # apply
  python scripts/upgrade_substreams.py --only jacuzzi,event_hall
  python scripts/upgrade_substreams.py --width 1920 --height 1080 --fps 15 --bitrate 3000
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
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


def _patch_tag(xml: str, tag: str, value) -> str:
    """Replace <tag>...</tag> if present; if absent, leave xml unchanged."""
    return re.sub(rf"<{tag}>.*?</{tag}>", f"<{tag}>{value}</{tag}>", xml, count=1)


def _read_tag(xml: str, tag: str) -> str:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", xml)
    return m.group(1) if m else ""


def _summary(xml: str) -> str:
    w = _read_tag(xml, "videoResolutionWidth")
    h = _read_tag(xml, "videoResolutionHeight")
    fps_raw = _read_tag(xml, "maxFrameRate")
    fps = f"{int(fps_raw) / 100:g}" if fps_raw.isdigit() else "?"
    codec = _read_tag(xml, "videoCodecType")
    qctrl = _read_tag(xml, "videoQualityControlType")
    cbr = _read_tag(xml, "constantBitRate")
    vbr = _read_tag(xml, "vbrUpperCap")
    br = cbr or vbr
    return f"{codec} {w}x{h} @ {fps}fps  {qctrl}  ~{br}kb/s"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--bitrate", type=int, default=2048,
                    help="VBR upper cap (kbps); also sets CBR if profile is CBR")
    ap.add_argument("--codec", default="H.264", choices=["H.264", "H.265"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", help="comma-separated camera ids to include")
    ap.add_argument("--cameras", default="backend/cameras.json")
    ap.add_argument("--backup-dir", default="eval/substream_backup",
                    help="save the original XML per channel here before PUT "
                         "(restore later by PUT'ing the file back)")
    args = ap.parse_args()
    backup_dir = Path(args.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    spec = json.loads(Path(args.cameras).read_text(encoding="utf-8"))
    cams = spec.get("cameras", [])
    if args.only:
        wanted = {x.strip() for x in args.only.split(",")}
        cams = [c for c in cams if c["id"] in wanted]

    fps_raw = args.fps * 100  # Hikvision encodes fps as fps*100
    n_ok, n_fail, n_skip = 0, 0, 0

    print(f"target  : {args.codec} {args.width}x{args.height} @ {args.fps}fps  ~{args.bitrate}kb/s")
    print(f"mode    : {'DRY RUN — no PUTs' if args.dry_run else 'APPLY'}")
    print()

    for c in cams:
        tag = str(c.get("nvr", ""))
        ip, user, pw = _nvr_creds(tag)
        if not ip or not pw:
            print(f"  [skip] {c['id']:<14} no creds for {tag}")
            n_skip += 1
            continue
        sub_ch = int(c["channel"])
        url = f"http://{ip}/ISAPI/Streaming/channels/{sub_ch}"
        auth = HTTPDigestAuth(user, pw)

        try:
            r = requests.get(url, auth=auth, timeout=8)
        except requests.RequestException as e:
            print(f"  [fail] {c['id']:<14} GET error: {e}")
            n_fail += 1
            continue
        if r.status_code != 200:
            print(f"  [fail] {c['id']:<14} GET HTTP {r.status_code}")
            n_fail += 1
            continue

        before = r.text
        after = before
        after = _patch_tag(after, "videoCodecType", args.codec)
        after = _patch_tag(after, "videoResolutionWidth", args.width)
        after = _patch_tag(after, "videoResolutionHeight", args.height)
        after = _patch_tag(after, "maxFrameRate", fps_raw)
        # bitrate: prefer VBR (smoother for motion) — set upper cap and CBR field
        # for cameras that report VBR-as-CBR fields.
        after = _patch_tag(after, "vbrUpperCap", args.bitrate)
        after = _patch_tag(after, "constantBitRate", args.bitrate)

        same = after == before
        print(f"  {c['id']:<14} ch={sub_ch}  before: {_summary(before)}")
        print(f"  {' ':<14}        after : {_summary(after)}{'   (no change)' if same else ''}")

        if same or args.dry_run:
            if not same:
                n_ok += 1  # would-have-applied counts in dry-run
            continue

        # backup original XML so we can restore if needed
        bkp = backup_dir / f"{c['id']}_ch{sub_ch}.xml"
        bkp.write_text(before, encoding="utf-8")

        # PUT new config
        try:
            pr = requests.put(url, data=after,
                              headers={"Content-Type": "application/xml"},
                              auth=auth, timeout=10)
        except requests.RequestException as e:
            print(f"  [fail] {c['id']:<14} PUT error: {e}")
            n_fail += 1
            continue
        if pr.status_code not in (200, 202):
            print(f"  [fail] {c['id']:<14} PUT HTTP {pr.status_code}: {pr.text[:120]}")
            n_fail += 1
            continue

        # verify
        try:
            vr = requests.get(url, auth=auth, timeout=8)
            verify = _summary(vr.text) if vr.status_code == 200 else "verify GET failed"
        except requests.RequestException as e:
            verify = f"verify err: {e}"
        print(f"  [ ok ] {c['id']:<14}    verify: {verify}")
        n_ok += 1

    print()
    print(f"applied: {n_ok}   failed: {n_fail}   skipped: {n_skip}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
