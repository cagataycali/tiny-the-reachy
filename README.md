<div align="center">

# `tiny` 🤖

**Strands agent driving a Reachy Mini** · _expressive · conversational · on the desk_

[![status](https://img.shields.io/badge/status-scaffold-00f0ff?style=flat-square)](#status)
[![robot](https://img.shields.io/badge/robot-Reachy_Mini-b967ff?style=flat-square)](https://www.pollen-robotics.com/reachy-mini/)
[![family](https://img.shields.io/badge/family-neon_·_scout_·_tiny-ff2a6d?style=flat-square)](#-the-family)
[![license](https://img.shields.io/badge/license-MIT-00ff88?style=flat-square)](LICENSE)

</div>

---

```
🎙 user (voice):  "hey tiny, what can you do?"
🤖 tiny:          "I can look around, wiggle my antennas, spin my body,
                   play emotions, take photos, and remember things!"
    → reachy_express('happy')  ·  antennas wiggle  ·  head tilt
🎙 user (voice):  "look at me"
    → take_photo(question="who's there?")  → sees you → replies aloud

💬 telegram /state
🤖 head_pose + antennas + imu snapshot
```

TINY is **one** agent with **four** personas — REPL, voice, telegram, thinker —
all sharing the same memory, the same toolset (14 robot tools + memory +
telegram + voice_say + take_photo + dispatch + ...), and the same cross-persona
log. Talk to it via the mic, DM it on Telegram, or `make run` for a REPL —
they all see what the others are doing.

**This is the exact same architecture as [`neon-the-g1`](../neon-the-g1) and
[`scout-the-rover`](../scout-the-rover)** — retargeted from a humanoid / rover
onto Pollen Robotics' expressive desktop robot. The cross-persona nervous
system (memory + agent_log + voice_bridge) is copied verbatim; only the robot
tool layer changes.

## 🔌 Use as an MCP server

Drive Tiny from **Claude Code, Claude Desktop, Cursor, Kiro, or any MCP client** — all 14 Reachy tools become MCP tools (motion, emotions, camera, audio).

```bash
# from a clone (with requirements.txt installed in the venv):
pip install -r requirements.txt strands-mcp-server
claude mcp add tiny -- $(pwd)/.venv/bin/python $(pwd)/mcp_server_entry.py
```

Options:

```bash
python mcp_server_entry.py --tools reachy_express,reachy_camera   # expose a subset
python mcp_server_entry.py --http --port 8090                     # HTTP mode, multi-client
```

> Tools connect to the robot lazily. The server starts without hardware — individual tool calls fail cleanly if the Reachy daemon (`:8000`) isn't running. Bring up the daemon first (real robot or `make sim`).

**The other direction — Tiny as an MCP *client*.** With `TINY_MCP=1` the personas mount the [tiny.technology](https://tiny.technology) MCP server (`tiny-tech`) as Strands tools: `use_device` reaches the owner's other devices (fomo the arm, q-the-brain, the Mac, Scout the rover), `tiny_recall`/`tiny_learn` share memory across agents. Curated allow-list, self-invoke refused, cross-device chains capped at depth 1, fail-open when node/token are missing. See [docs/MCP.md](docs/MCP.md).

---

## 🧬 the family

| robot | body | control layer | this repo mirrors |
|---|---|---|---|
| **NEON** | Unitree G1 humanoid | DDS / FSM-gated arms+legs | `g1.py`, `tools/g1_*` |
| **SCOUT** | rover | ROS / velocity | `agent.py`, `tools/` |
| **TINY** | Reachy Mini | Reachy SDK → daemon `:8000` | `tiny.py`, `tools/reachy_*` |

Same shared brain. Same 4 personas. Same docker-compose + systemd deploy.

## ⚡ run

```bash
cp .env.example .env && $EDITOR .env   # AWS_BEARER_TOKEN_BEDROCK + OPENAI_API_KEY + TELEGRAM_BOT_TOKEN
make venv                              # create .venv + install deps
make run                               # REPL agent (needs the Reachy daemon up)
make sim                               # ...or run against MuJoCo simulation (no hardware)
```

The **Reachy Mini daemon** owns the hardware and exposes an HTTP/WS API on
`:8000`. On the **Lite** it runs on your laptop (`localhost:8000`); on the
**Wireless** it runs on the onboard CM4 (`reachy-mini.local:8000`). TINY's
agents are pure clients of that daemon — set `REACHY_HOST` / `REACHY_PORT` /
`REACHY_CONNECTION_MODE` in `.env` (defaults auto-detect).

## 🛰 deploy — full stack in docker, boots on power-on

Three always-on personas run as containers and start automatically at boot via
one systemd user unit (`tiny-compose.service` → `docker compose up -d`):

```bash
cp .env.example .env && $EDITOR .env
make build                                # build the tiny image (light — no DDS/realsense)
make up                                   # voice + telegram + thinker

# install the boot unit (survives reboot; linger must be on)
make install-compose-service
```

Containers (`docker compose up -d`):

| container | role |
|---|---|
| `tiny-voice` | always-on bidirectional voice (local mic → speaker, head-wobble on speech) |
| `tiny-telegram` | Telegram DM listener → spawns a telegram-persona agent per message |
| `tiny-thinker` | 30s heartbeat → photo + one expression + telegram status + journal |

All three share the SQLite brain at `.memory/mem.db` (mounted into every
container) and all connect to the Reachy daemon over host networking.

> **Bare-metal alternative** (run directly on the CM4, no docker):
> `make venv && make install-bare-services` installs
> `tiny-voice` / `tiny-telegram` / `tiny-thinker` as user systemd units.

## 🧰 toolkit

| bundle | tools |
|---|---|
| **motion** | `reachy_look` (6-DOF head), `reachy_antennas`, `reachy_body_turn`, `reachy_home`, `reachy_wake` |
| **expression** | `reachy_express` (emotion library), `reachy_list_emotions` |
| **state** | `reachy_get_state` (pose + IMU), `reachy_motors` (torque modes) |
| **sensing** | `reachy_camera`, `reachy_look_at`, `take_photo` (bidi vision) |
| **audio** | `reachy_say` (TTS + head-wobble), `reachy_play_sound`, `reachy_volume` |
| **cross-persona** | `memory`, `voice_say`, `telegram`, `dispatch`, `agent_log`, `prompts`, `manage_*` |

14 robot tools + the shared lookout-stack. All FSM-free (Reachy Mini has no
gait/arms to gate) but clamped to the head/body/antenna safety envelope.

## 🎭 expression = personality

Reachy Mini has no arms or legs — its whole personality is head + body +
antennas + the recorded-emotion library
(`pollen-robotics/reachy-mini-emotions-library`). TINY fires expressions
**simultaneously with speech**, exactly like NEON fires arm gestures:

```
"hi"           → reachy_express('happy')  or reachy_antennas(45, 45)
"yes"          → nod  (reachy_look pitch up then down)
"no"           → reachy_express('no')  (head shake)
curious         → reachy_express('curious') / reachy_look(roll=15)
excited         → reachy_antennas(60,60) + reachy_body_turn(20)
```

## 🎙 voice + 💬 telegram + 🧠 thinker

```bash
make voice        # bidirectional voice (local mic → speaker)
make tg           # telegram bot (multi-turn + /mute /state /wake)
make thinker      # 30s expressive heartbeat loop
make mute/unmute  # silence the voice agent live
make log-show     # last 30 cross-persona turns
make ask Q="say hi and wobble your antennas"
```

**Cross-persona awareness**: when telegram receives a message it's pushed to
`voice_bridge` so the voice persona hears it as a `[BRIEFING]`. All personas
share `.memory/mem.db` — voice can pick up where telegram left off.

## 🧪 safety envelope

| joint | range |
|---|---|
| head pitch / roll | [-40, +40]° |
| head yaw | [-180, +180]° |
| body yaw | [-160, +160]° |
| head−body yaw delta | max 65° |

The SDK clamps automatically; our wrappers also clamp + surface the limits.
Gentle collisions with the body are safe.

## 🖥 dashboard — reachy.cagatay.my

Passkey-gated cockpit that runs **on the robot** (`dashboard/`, FastAPI :8097 behind cloudflared): live camera with the
MuJoCo **digital twin as a picture-in-picture card** (drag to a corner, double-tap to swap, readout of head R/P/Y ·
body yaw · antennas · loop Hz · motor mode), TINY's mind as bubbles over the picture, look/emotions/say/settings docks,
STOP always in reach. → [`docs/DASHBOARD.md`](docs/DASHBOARD.md) · [`dashboard/README.md`](dashboard/README.md)

## 🚦 status

| component | status | notes |
|---|---|---|
| 🤖 robot tools | 🟡 scaffold | 14 tools wired to Reachy SDK; verified against SDK 1.9 API |
| 🎙 voice (bidi) | 🟡 scaffold | OpenAI Realtime / Nova Sonic / Gemini, local PyAudio IO |
| 💬 telegram | 🟡 scaffold | multi-turn + slash commands, copied from neon |
| 🧠 thinker | 🟡 scaffold | 30s photo + expression + telegram heartbeat |
| 🐳 docker stack | 🟡 scaffold | light image (no DDS/realsense build) |
| 🛰 systemd | 🟡 scaffold | compose unit + 3 bare-metal units |
| ✅ smoke tests | 🟢 pass | `make test-tools` — imports + prompts + clamps |

## 🙏 built on

[strands-agents](https://github.com/strands-agents) ·
[devduck](https://github.com/cagataycali/devduck) ·
[reachy_mini](https://github.com/pollen-robotics/reachy_mini) (Pollen Robotics) ·
sibling to [neon-the-g1](../neon-the-g1) + [scout-the-rover](../scout-the-rover)

MIT license.
