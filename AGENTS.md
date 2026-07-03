# AGENTS.md — Navigation Guide for `tiny-the-reachy`

> **Purpose**: fast orientation for any AI agent working in this directory.
> Human-facing usage → `README.md`. This is the map + the hard-won facts.

TINY is a Strands agent embodying a **Reachy Mini** (Pollen Robotics). It is a
direct sibling of `neon-the-g1` and `scout-the-rover` — SAME shared-brain
architecture, DIFFERENT robot body. If you know neon, you know tiny.

---

## 🗺️ Directory Map

```
tiny-the-reachy/
├── tiny.py               ← THE agent factory (single source of truth)
│                            build_agent(persona) / build_shell_agent() /
│                            build_voice_agent() — 4 personas, one tool list.
│                            ⇔ neon's g1.py
├── agent.py              ← REPL entry point (shell persona)
├── voice_listener.py     ← always-on bidi voice persona
├── telegram_listener.py  ← telegram persona (spawn agent per message)
├── thinker_loop.py       ← 30s expressive heartbeat persona
├── prompts/base.md       ← TINY persona (edit without touching code)
│
├── tools/
│   ├── __init__.py           ← exports TINY_ALL_TOOLS / bundles
│   ├── _reachy_common.py     ← cached ReachyMini singleton + clamp + ok/err
│   │  # ── robot control (Reachy SDK → daemon :8000) ──
│   ├── reachy_motion.py      ← reachy_look / antennas / body_turn / home / wake
│   ├── reachy_expression.py  ← reachy_express (emotion lib) / list_emotions
│   ├── reachy_state.py       ← reachy_get_state (pose+IMU) / reachy_motors
│   ├── reachy_camera.py      ← reachy_camera / reachy_look_at
│   ├── reachy_audio.py       ← reachy_say (TTS+wobble) / play_sound / volume
│   ├── vision.py             ← take_photo (bidi image injection)
│   │  # ── cross-persona brain (COPIED VERBATIM from neon) ──
│   ├── memory.py             ← SQLite kv/log + fs notes
│   ├── agent_log.py          ← unified cross-persona reasoning log
│   ├── voice_bridge.py       ← briefing queue → voice persona
│   ├── telegram.py           ← Telegram Bot API + per-chat history
│   ├── dispatch.py           ← spawn devduck sub-agents (cron/run_at)
│   ├── prompts.py            ← per-persona prompt overrides (SQLite)
│   ├── manage_messages.py    ← trim/compact own history
│   └── manage_tools.py       ← load/create tools at runtime
│
├── Dockerfile            ← light image (NO DDS/realsense build — unlike neon)
├── docker-compose.yml    ← tiny-voice + tiny-telegram + tiny-thinker
├── scripts/systemd/
│   ├── tiny-compose.service   ← docker stack boot unit (user systemd)
│   ├── tiny-voice.service     ← bare-metal voice unit
│   ├── tiny-telegram.service  ← bare-metal telegram unit
│   └── tiny-thinker.service   ← bare-metal thinker unit
├── requirements.txt      ← strands + reachy_mini[opencv,examples] + devduck
├── Makefile              ← operational verbs (make help)
└── tests/test_import.py  ← smoke test (no robot needed)
```

---

## 🚀 Quick-Start

```bash
make venv                    # .venv + deps
make test-tools              # smoke test (imports + prompts + clamps) — NO robot needed
make sim                     # REPL against MuJoCo (no hardware)
make run                     # REPL against the real daemon
make ask Q="say hi and wobble your antennas"
```

---

## 🧠 The Four Personas (one brain)

```
   shell agent    ◄── agent.py REPL (you, interactively)
   voice agent    ◄── voice_listener.py (bidi realtime, local mic+speaker)
   telegram agent ◄── telegram_listener.py (incoming DM → spawn agent)
   thinker agent  ◄── thinker_loop.py (30s expressive heartbeat)

   ALL share: .memory/mem.db (kv, log, agent_log, voice_bridge, tg_history, prompts)
```

Every persona is built by `tiny.build_agent(persona)` / `build_voice_agent()`.
When persona A does something, all OTHER personas SEE IT via the "Unified
Reasoning Log" block injected into their prompts (via `agent_log.format_for_prompt`).

Inbound async messages flow telegram → `voice_bridge.push()` → voice persona
hears a `[BRIEFING]` and can speak it. Identical to neon.

---

## 🤖 The Robot Layer (what's DIFFERENT from neon)

Reachy Mini has **no arms, no legs, no gait, no FSM**. Control is dead simple:
a `ReachyMini()` client talks to a **daemon on `:8000`** over HTTP/WS. There is
NO DDS, NO CycloneDDS, NO librealsense — the Docker image is light.

**Connection** (`tools/_reachy_common.get_mini()`, cached singleton):
- Lite:      daemon on host laptop → `localhost:8000` (`REACHY_CONNECTION_MODE=auto`)
- Wireless:  daemon on the CM4     → `reachy-mini.local:8000`
- Sim:       `REACHY_USE_SIM=1` → MuJoCo, no hardware

**Expression = personality.** No gestures via arms — instead:
- 6-DOF head pose (`reachy_look`: x,y,z mm + roll,pitch,yaw deg)
- body yaw (`reachy_body_turn`)
- 2 antennas / "ears" (`reachy_antennas`)
- recorded-emotion library (`reachy_express` → `pollen-robotics/reachy-mini-emotions-library`)

Fire expressions SIMULTANEOUSLY with speech (see `prompts/base.md` playbook).

---

## 🧪 Safety Envelope (SDK clamps; we clamp too)

| joint | range |
|---|---|
| head pitch/roll | [-40, +40]° |
| head yaw | [-180, +180]° |
| body yaw | [-160, +160]° |
| head−body yaw delta | max 65° |

`_reachy_common.clamp()` enforces this in `reachy_look` / `reachy_body_turn`.
Gentle body collisions are safe. Small moves look most natural.

---

## 🔧 Extension Pattern (new robot tool)

```python
# tools/reachy_something.py
from strands import tool
from ._reachy_common import get_mini, clamp, ok, err

@tool
def reachy_something(param: float = 0.0) -> dict:
    """One-line intent the LLM reads to decide when to call this."""
    try:
        mini = get_mini()          # cached singleton — never re-connect
        mini.some_sdk_method(param)
        return ok(f"did something with {param}")
    except Exception as e:
        return err(f"reachy_something failed: {e}")
```

Then export it in `tools/__init__.py` and add to the right bundle
(`TINY_MOTION_TOOLS`, etc.). Use `get_mini()` — DO NOT construct `ReachyMini`
yourself (it's a cached singleton; re-connecting fights the daemon).

Verified SDK methods our tools rely on (SDK 1.9): `goto_target`, `set_target`,
`wake_up`, `goto_sleep`, `get_current_head_pose`, `get_current_joint_positions`,
`enable_motors`, `disable_motors`, `enable_gravity_compensation`,
`look_at_image`, `play_move`, `enable_wobbling`, `media.get_frame`,
`media.play_sound`, `imu`. Emotion catalogue via `RecordedMoves.list_moves()`.

---

## 🛰 Deploy (same shape as neon)

**Docker** (recommended): `make build && make up && make install-compose-service`
→ `tiny-voice` + `tiny-telegram` + `tiny-thinker` boot on power-on, share
`.memory/`, connect to the daemon over host networking.

**Bare-metal** (on the CM4): `make venv && make install-bare-services`
→ 3 user systemd units. `After=reachy-mini.service` so they wait for the daemon.

---

## ✅ TL;DR for agents entering this directory

1. `make test-tools` first — it proves everything imports without a robot.
2. All persona/tool/prompt logic lives in `tiny.py` — ONE source of truth.
3. Robot tools go through `get_mini()` (cached client) — never reconnect.
4. Expression IS the personality — use `reachy_express` + antennas + head.
5. Clamp to the head/body/antenna envelope; small moves look best.
6. The cross-persona brain (`tools/memory|agent_log|voice_bridge|...`) is copied
   verbatim from neon — don't reinvent it; it just works.
