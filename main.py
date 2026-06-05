"""CLI entrypoint.

Usage:
  python main.py                 # run the agent with conditions.yaml
  python main.py --check         # test camera connection + list relay outputs
  python main.py --once          # grab a single frame, evaluate once, exit
"""
from __future__ import annotations

import argparse
import os

from watchful.act import Actuator
from watchful.agent import Agent
from watchful.config import CameraConfig, load_conditions
from watchful.perceive import FrameSource
from watchful.understand import VLM


def build():
    camera = CameraConfig.from_env()
    conditions = load_conditions(os.environ.get("CONDITIONS_PATH", "conditions.yaml"))
    actuator = Actuator(camera, webhook_url=os.environ.get("WEBHOOK_URL"))
    source = FrameSource(camera)
    vlm = VLM()
    return camera, conditions, actuator, source, vlm


def main():
    ap = argparse.ArgumentParser(description="Watchful camera agent")
    ap.add_argument("--check", action="store_true", help="test connection + list relays")
    ap.add_argument("--once", action="store_true", help="evaluate one frame and exit")
    ap.add_argument("--poll", type=float, default=0.5, help="seconds between polls")
    ap.add_argument("--no-motion-gate", action="store_true")
    args = ap.parse_args()

    camera, conditions, actuator, source, vlm = build()

    if args.check:
        print("RTSP URL:", camera.rtsp_url.replace(camera.password, "***"))
        source.open()
        frame = source.read()
        print("Frame grabbed:", None if frame is None else frame.shape)
        source.close()
        print("\nRelay outputs (ISAPI):")
        print(actuator.list_outputs())
        return

    agent = Agent(
        source, conditions, actuator, vlm,
        poll_interval=args.poll,
        use_motion_gate=not args.no_motion_gate,
        on_event=lambda e: print("[event]", e),
    )

    if args.once:
        source.open()
        agent.step()
        source.close()
        return

    agent.run()


if __name__ == "__main__":
    main()
