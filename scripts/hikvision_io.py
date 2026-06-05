"""Hikvision relay / alarm-output control via ISAPI (digest auth).

SAFE BY DEFAULT: with no --trigger it only READS (lists outputs + their state),
which has no physical side effect. Triggering an output may physically actuate
whatever is wired to it (light, lock, siren) — only with --trigger and --confirm.

Reads NVR passwords from .env (NVR1_PASS / NVR2_PASS).

  # read-only discovery:
  python scripts/hikvision_io.py --nvr NVR2
  # actually fire output 1 high for 2s (DOUBLE opt-in):
  python scripts/hikvision_io.py --nvr NVR2 --trigger 1 --state high --confirm
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests
from requests.auth import HTTPDigestAuth

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def load_env(path=".env") -> dict:
    env = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def get(base, path, auth):
    try:
        r = requests.get(base + path, auth=auth, timeout=8)
        return r.status_code, r.text
    except Exception as e:
        return None, str(e)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nvr", default="NVR2", choices=["NVR1", "NVR2"])
    ap.add_argument("--port", type=int, default=80)
    ap.add_argument("--trigger", type=int, default=None, help="output id to fire")
    ap.add_argument("--state", default="high", choices=["high", "low"])
    ap.add_argument("--seconds", type=float, default=2.0, help="hold then revert")
    ap.add_argument("--confirm", action="store_true", help="required to actually fire")
    args = ap.parse_args()

    env = load_env()
    ip = env[f"{args.nvr}_IP"]
    pw = env[f"{args.nvr}_PASS"]
    user = env.get(f"{args.nvr}_USER", "admin")
    auth = HTTPDigestAuth(user, pw)
    base = f"http://{ip}:{args.port}"
    print(f"=== {args.nvr} {ip}:{args.port} ===")

    # ---- READ-ONLY discovery ----
    code, body = get(base, "/ISAPI/System/IO/outputs", auth)
    print(f"GET /ISAPI/System/IO/outputs -> {code}")
    if code == 200:
        import re
        ids = re.findall(r"<id>(\d+)</id>", body)
        print(f"  output ids: {ids or '(none parsed)'}")
        print("  --- raw (first 800 chars) ---")
        print("  " + body[:800].replace("\n", "\n  "))
        for oid in ids:
            sc, st = get(base, f"/ISAPI/System/IO/outputs/{oid}/status", auth)
            sstate = re.findall(r"<ioState>(\w+)</ioState>", st)
            print(f"  output {oid} status -> {sc}  state={sstate}")
    else:
        print(f"  body: {body[:300]}")

    # also check capabilities (how many alarm outputs the device claims)
    code2, body2 = get(base, "/ISAPI/System/IO/capabilities", auth)
    if code2 == 200:
        import re
        no = re.findall(r"<outputNums>(\d+)</outputNums>", body2)
        print(f"  IO capabilities outputNums={no}")

    # ---- TRIGGER (guarded) ----
    if args.trigger is not None:
        if not args.confirm:
            print("\n  REFUSING to fire: pass --confirm to actually trigger "
                  "(this may physically actuate hardware).")
            return
        oid = args.trigger
        xml = f"<IOPortData><outputState>{args.state}</outputState></IOPortData>"
        url = base + f"/ISAPI/System/IO/outputs/{oid}/trigger"
        print(f"\n  FIRING output {oid} -> {args.state} for {args.seconds}s ...")
        r = requests.put(url, auth=auth, data=xml, timeout=8)
        print(f"  PUT trigger -> {r.status_code}: {r.text[:200]}")
        time.sleep(args.seconds)
        rev = "low" if args.state == "high" else "high"
        xml2 = f"<IOPortData><outputState>{rev}</outputState></IOPortData>"
        r2 = requests.put(url, auth=auth, data=xml2, timeout=8)
        print(f"  revert -> {rev}: {r2.status_code}")


if __name__ == "__main__":
    main()
