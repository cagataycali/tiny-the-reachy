#!/usr/bin/env python3
"""🧠 TINY Slow-Thinker — background reflective/expressive loop (every ~30s).

Same pattern as neon-the-g1's thinker: build a fresh 'thinker' persona agent,
refresh its (dynamic) system prompt each cycle, kick it to DO something
expressive + take a photo + telegram a heartbeat + journal it.

Env:
  THINKER_INTERVAL   seconds between cycles (default 30)
  THINKER_DISABLED   "1" to no-op
"""
import os
import sys
import signal
import time
import traceback
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.agent_log import record as alog
from tools import config as _config
from tiny import build_agent, _thinker_prompt

INTERVAL = int(os.getenv("THINKER_INTERVAL", "30"))
DISABLED = os.getenv("THINKER_DISABLED", "").lower() in ("1", "true", "yes")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class _AgentHolder:
    """The thinker's Agent plus the config generation it was built at: a cockpit change to the model id or the
    thinker's tool list (`agent` restart scope, tools/config.py) rebuilds it at the start of the next cycle."""

    def __init__(self) -> None:
        self.agent = None
        self.generation = -1

    def current(self):
        gen = _config.generation("agent")
        if self.agent is None or gen != self.generation:
            if self.agent is not None:
                print(f"[{_now()}] 🧠 config generation {self.generation} -> {gen}: rebuilding the thinker agent", flush=True)
                alog("thinker", "system", f"config generation {self.generation} -> {gen}: agent rebuilt")
            self.agent = build_agent("thinker")
            self.generation = gen
        return self.agent


def cycle(agent) -> None:
    t0 = time.time()
    print(f"[{_now()}] 🧠 thinker cycle start", flush=True)
    try:
        agent.messages.clear()
    except Exception:
        pass
    try:
        agent.system_prompt = _thinker_prompt()
    except Exception as e:
        print(f"[{_now()}] ⚠️ prompt refresh failed: {e}", flush=True)
    photos = bool(_config.get("telegram.heartbeat_photos")) and bool(_config.get("telegram.default_chat_id"))
    step3 = ("  3. telegram(action='send_photo', chat_id from the prompt, "
             "file_path='/tmp/tiny_view.jpg', caption='<1 sentence: what TINY saw + did>').\n"
             if photos else
             "  3. NO telegram this cycle (heartbeat photos are off in the cockpit) — skip send_photo/send_message.\n")

    user_turn = (
        "Run an active heartbeat cycle. TINY is alive — show it.\n"
        "MANDATORY (do 1+3+4 every time, VARY step 2):\n"
        "  1. capture_camera(save_path='/tmp/tiny_view.jpg') — ONE call: the frame lands in your context AND is saved\n"
        "     to /tmp/tiny_view.jpg for step 3 (do not call reachy_camera + image_reader).\n"
        "  2. PICK ONE expressive action — ROTATE, do NOT repeat last cycle:\n"
        "       (a) reachy_express('happy'|'curious'|'surprised'|'sad'|'yes'|'no')\n"
        "       (b) reachy_antennas(right, left)  — always safe\n"
        "       (c) reachy_look(pitch=, yaw=, roll=)  — gentle head move\n"
        "       (d) reachy_body_turn(yaw=±30)  — small scan\n"
        + step3 +
        "  4. memory(action='log_add', text='<one line>', tag='thinker').\n"
        "Do steps in parallel where possible. Be terse. TINY is a small robot with "
        "a big personality — no 'as an AI' energy. ONE action, then ship it."
    )
    try:
        result = agent(user_turn)
        text = str(result)[:1500]
        alog("thinker", "assistant", text)
        print(f"[{_now()}] 🧠 thinker → {text[:200]}", flush=True)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        print(f"[{_now()}] ❌ thinker cycle error: {err}", flush=True)
        traceback.print_exc()
        alog("thinker", "system", f"cycle error: {err}")
    print(f"[{_now()}] 🧠 thinker cycle done in {time.time()-t0:.1f}s", flush=True)


def main():
    print(f"🧠 TINY Slow-Thinker starting (interval={INTERVAL}s)")
    if DISABLED:
        print("THINKER_DISABLED=1 — exiting")
        return
    stop = {"flag": False}
    def _sig(*_):
        stop["flag"] = True
        print(f"\n[{_now()}] 🧠 stop requested", flush=True)
    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    holder = _AgentHolder()
    try:
        agent = holder.current()
        print(f"[{_now()}] 🧠 thinker agent built ({len(agent.tool_names)} tools, config generation {holder.generation})", flush=True)
    except Exception as e:
        print(f"❌ failed to build thinker agent: {e}")
        traceback.print_exc()
        sys.exit(1)

    for _ in range(min(INTERVAL, 15)):
        if stop["flag"]:
            return
        time.sleep(1)

    while not stop["flag"]:
        try:
            cycle(holder.current())
        except Exception as e:
            print(f"[{_now()}] ❌ outer cycle error: {e}", flush=True)
            traceback.print_exc()
        for _ in range(INTERVAL):
            if stop["flag"]:
                break
            time.sleep(1)
    print(f"[{_now()}] 👋 thinker stopped")


if __name__ == "__main__":
    main()
