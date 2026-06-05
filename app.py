"""Streamlit UI (stretch goal) — add/edit natural-language conditions and
run the agent in the background.

  streamlit run app.py
"""
from __future__ import annotations

import threading

import streamlit as st

from watchful.act import Actuator
from watchful.agent import Agent
from watchful.config import (
    Action,
    CameraConfig,
    Condition,
    load_conditions,
    save_conditions,
)
from watchful.perceive import FrameSource
from watchful.understand import VLM

st.set_page_config(page_title="Watchful", page_icon="👁️", layout="wide")
st.title("👁️ Watchful — tell the camera what to watch for")

if "conditions" not in st.session_state:
    try:
        st.session_state.conditions = load_conditions()
    except Exception:
        st.session_state.conditions = []
if "log" not in st.session_state:
    st.session_state.log = []
if "agent" not in st.session_state:
    st.session_state.agent = None

left, right = st.columns([2, 1])

with left:
    st.subheader("Conditions")
    for i, c in enumerate(st.session_state.conditions):
        with st.expander(f"{'✅' if c.enabled else '⬜'} {c.id}", expanded=False):
            c.prompt = st.text_area("Watch for (plain English)", c.prompt, key=f"p{i}")
            cols = st.columns(3)
            c.confidence_min = cols[0].slider("min confidence", 0.0, 1.0, c.confidence_min, key=f"cf{i}")
            c.hits_needed = cols[1].number_input("hits needed", 1, 600, c.hits_needed, key=f"h{i}")
            c.cooldown_seconds = cols[2].number_input("cooldown (s)", 0, 3600, c.cooldown_seconds, key=f"cd{i}")
            c.enabled = st.checkbox("enabled", c.enabled, key=f"e{i}")
            act = c.actions[0] if c.actions else Action(type="relay", port=1)
            acols = st.columns(4)
            act.type = acols[0].selectbox("action", ["relay", "notify", "log"],
                                          index=["relay", "notify", "log"].index(act.type), key=f"at{i}")
            if act.type == "relay":
                act.port = acols[1].number_input("port", 1, 16, act.port or 1, key=f"ap{i}")
                act.state = acols[2].selectbox("state", ["on", "off"],
                                               index=0 if act.state == "on" else 1, key=f"as{i}")
                act.duration_seconds = acols[3].number_input("duration (s, 0=hold)", 0, 7200,
                                                             act.duration_seconds or 0, key=f"ad{i}") or None
            else:
                act.message = acols[1].text_input("message", act.message, key=f"am{i}")
            c.actions = [act]

    st.markdown("---")
    st.subheader("Add a condition")
    with st.form("add", clear_on_submit=True):
        new_id = st.text_input("id", placeholder="jacuzzi-hand-raise")
        new_prompt = st.text_input("Watch for", placeholder="someone in the jacuzzi raises their hand")
        if st.form_submit_button("Add") and new_id and new_prompt:
            st.session_state.conditions.append(
                Condition(id=new_id, prompt=new_prompt,
                          actions=[Action(type="relay", port=1, state="on", duration_seconds=300)])
            )
            st.rerun()

    if st.button("💾 Save to conditions.yaml"):
        save_conditions(st.session_state.conditions)
        st.success("Saved.")

with right:
    st.subheader("Agent")
    running = st.session_state.agent is not None
    st.write("Status:", "🟢 running" if running else "⚪ stopped")

    if not running and st.button("▶ Start"):
        camera = CameraConfig.from_env()
        actuator = Actuator(camera)
        source = FrameSource(camera)
        agent = Agent(source, st.session_state.conditions, actuator, VLM(),
                      on_event=lambda e: st.session_state.log.insert(0, e))
        t = threading.Thread(target=agent.run, daemon=True)
        t.start()
        st.session_state.agent = agent
        st.rerun()

    if running and st.button("⏹ Stop"):
        st.session_state.agent.stop()
        st.session_state.agent = None
        st.rerun()

    st.subheader("Live events")
    for e in st.session_state.log[:30]:
        st.json(e, expanded=False)
