"""Restore each sub-stream's original XML from the backup made by
upgrade_substreams.py (--backup-dir).

Each backup file is named <cam_id>_ch<channel>.xml and contains the exact XML
that was on the NVR before the upgrade. This script PUTs each file back.

Usage:
  python scripts/restore_substreams.py
  python scripts/restore_substreams.py --backup-dir eval/substream_backup
  python scripts/restore_substreams.py --only jacuzzi
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backup-dir", default="eval/substream_backup")
    ap.add_argument("--only", help="comma-separated camera ids to include")
    ap.add_argument("--cameras", default="backend/cameras.json")
    args = ap.parse_args()

    spec = json.loads(Path(args.cameras).read_text(encoding="utf-8"))
    cams = spec.get("cameras", [])
    if args.only:
        wanted = {x.strip() for x in args.only.split(",")}
        cams = [c for c in cams if c["id"] in wanted]

    backup_dir = Path(args.backup_dir)
    if not backup_dir.is_dir():
        print(f"backup dir not found: {backup_dir}")
        return 2

    n_ok, n_fail, n_skip = 0, 0, 0
    for c in cams:
        tag = str(c.get("nvr", ""))
        ip, user, pw = _nvr_creds(tag)
        if not ip or not pw:
            n_skip += 1
            continue
        sub_ch = int(c["channel"])
        bkp = backup_dir / f"{c['id']}_ch{sub_ch}.xml"
        if not bkp.exists():
            print(f"  [skip] {c['id']:<14} no backup file: {bkp.name}")
            n_skip += 1
            continue
        xml = bkp.read_text(encoding="utf-8")
        url = f"http://{ip}/ISAPI/Streaming/channels/{sub_ch}"
        try:
            r = requests.put(url, data=xml,
                             headers={"Content-Type": "application/xml"},
                             auth=HTTPDigestAuth(user, pw), timeout=10)
        except requests.RequestException as e:
            print(f"  [fail] {c['id']:<14} PUT error: {e}")
            n_fail += 1
            continue
        if r.status_code not in (200, 202):
            print(f"  [fail] {c['id']:<14} HTTP {r.status_code}: {r.text[:100]}")
            n_fail += 1
            continue
        # quick before/after summary
        w = re.search(r"<videoResolutionWidth>(.*?)</videoResolutionWidth>", xml)
        h = re.search(r"<videoResolutionHeight>(.*?)</videoResolutionHeight>", xml)
        print(f"  [ ok ] {c['id']:<14} restored to {w.group(1) if w else '?'}x{h.group(1) if h else '?'}")
        n_ok += 1

    print()
    print(f"restored: {n_ok}   failed: {n_fail}   skipped: {n_skip}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
