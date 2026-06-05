"""List all camera channels on a Hikvision NVR via ISAPI (HTTP digest auth).

  python scripts/list_channels.py --ip 192.168.0.59 --user admin --password "<NVR1_PASS>"
"""
from __future__ import annotations

import argparse
import re
import sys

import requests
from requests.auth import HTTPDigestAuth

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", required=True)
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", required=True)
    args = ap.parse_args()

    auth = HTTPDigestAuth(args.user, args.password)
    base = f"http://{args.ip}"

    # Try the streaming-channels listing first, then fall back to input channels.
    for path in ("/ISAPI/Streaming/channels", "/ISAPI/ContentMgmt/InputProxy/channels"):
        try:
            r = requests.get(base + path, auth=auth, timeout=8)
        except Exception as e:
            print(f"  {path} -> error: {e}")
            continue
        if r.status_code != 200:
            print(f"  {path} -> HTTP {r.status_code}")
            continue

        xml = r.text
        # crude XML scrape: pairs of <id>..</id> and <channelName>/<name>..
        ids = re.findall(r"<id>(\d+)</id>", xml)
        names = re.findall(r"<(?:name|channelName)>(.*?)</(?:name|channelName)>", xml)
        print(f"\n=== {args.ip}  ({path}) ===")
        if ids:
            for i, cid in enumerate(ids):
                nm = names[i] if i < len(names) else "?"
                print(f"  channel id={cid:<4} name={nm}")
        else:
            print(xml[:1500])
        return

    print("  Could not list channels via ISAPI.")


if __name__ == "__main__":
    main()
