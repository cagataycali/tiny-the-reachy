<div align="center">

# TINY · the Reachy Mini agent

**A Reachy Mini that listens, looks, talks back and remembers — a Strands agent living in a desk
robot.**

[![Docs](https://github.com/cagataycali/tiny-the-reachy/actions/workflows/docs.yml/badge.svg)](https://github.com/cagataycali/tiny-the-reachy/actions/workflows/docs.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-77718c)](Dockerfile)
[![Reachy Mini Wireless](https://img.shields.io/badge/hardware-Reachy_Mini_Wireless-77718c)](https://www.pollen-robotics.com/reachy-mini/)
[![MIT](https://img.shields.io/badge/license-MIT-77718c)](LICENSE)

[Docs](https://cagataycali.github.io/tiny-the-reachy/) · [Architecture](https://cagataycali.github.io/tiny-the-reachy/guide/architecture/) · [Quickstart](#quickstart) · [Personas](#personas) · [Cockpit](#cockpit) · [Tools](#tools) · [Hardware](https://www.pollen-robotics.com/reachy-mini/)

</div>

TINY lives inside a Pollen Robotics [Reachy Mini](https://github.com/pollen-robotics/reachy_mini).
Pollen's daemon drives the motors, camera and microphones; TINY, a
[Strands](https://github.com/strands-agents) agent, decides what to say, where to look and which
recorded emotion to play. Voice, Telegram, a background thinker, a terminal and the cockpit's Ask
box share one memory — talk to it at the desk, and it remembers when you message it from your phone.

## Architecture

```text
voice_listener.py  telegram_listener.py  thinker_loop.py  agent.py  dashboard Ask
        └──────────────┴──────────────┴──────────────┴──────────┘
                          tiny.py  — one factory, five personas
                          tools/   — 26 @tool functions
                        .memory/mem.db — shared kv · log · history
                                  │  HTTP / WS :8000
                   Pollen reachy-mini daemon → motors · camera · mics
```

## Quickstart

You need Python 3.12, a Reachy Mini daemon on `:8000` (Lite: your laptop; Wireless: the robot) and
Bedrock credentials for the text personas.

```bash
git clone https://github.com/cagataycali/tiny-the-reachy.git
cd tiny-the-reachy
cp .env.example .env      # AWS_BEARER_TOKEN_BEDROCK · REACHY_HOST · OPENAI_API_KEY (voice only)
make venv                 # .venv + requirements (+ PyAudio extras, best effort)
make run                  # REPL against the daemon
make ask Q="say hi and wiggle your antennas"
```

No robot? `make sim` points the same REPL at the MuJoCo simulator (`REACHY_USE_SIM=1`, spawns its
own daemon — don't run it beside a hardware daemon).

## Personas

| Persona | Run | What it does |
|---|---|---|
| Shell | `make run` · `make ask Q="..."` | REPL; refreshes live head/antenna state into the prompt every turn |
| Voice | `make voice` | Realtime audio through the robot's mics and speaker (OpenAI Realtime default; Nova Sonic, Gemini Live) |
| Telegram | `make tg` | Spawns one agent per message; per-chat history, sender allow-list, `/state /wake /sleep` answered without the model |
| Thinker | `make thinker` | Every ~30 s: photo, one expressive move, a Telegram heartbeat (if a chat is configured), a journal line |
| Dashboard Ask | cockpit Ask box | Runs one agent turn per question, streamed over the cockpit's WebSocket |

All five come from [`tiny.py`](tiny.py) and share `.memory/mem.db`; a shared agent log in every
prompt lets each persona see what the others just did.

## Cockpit

[`dashboard/`](dashboard/) is a FastAPI server (`:8097`) plus a React PWA, meant to run on the robot: live
camera with a MuJoCo twin picture-in-picture, the Ask box, emotions and a scripted reel, a look pad,
say/volume, face-tracking and turn-to-sound toggles, a demo mode that pauses the thinker, the shared
mind timeline, and STOP. Everything except `/api/health`, `/api/auth/*` and the sign-in shell
demands a passkey session or a bearer token.
[How it works →](https://cagataycali.github.io/tiny-the-reachy/DASHBOARD/)

## Tools

26 `@tool` functions in [`tools/`](tools/) — 19 for the robot, 7 for the shared brain. Voice and
Shell mount a slim subset for latency; Telegram and Thinker mount everything.

| Group | Tools |
|---|---|
| Motion | `reachy_look` `reachy_antennas` `reachy_body_turn` `reachy_home` `reachy_wake` |
| Expression | `reachy_express` (plain English → recorded emotion) `reachy_list_emotions` |
| State | `reachy_get_state` `reachy_motors` |
| Sensing | `reachy_camera` `capture_camera` `reachy_look_at` `head_tracking` `head_tracking_status` `turn_to_sound` `turn_to_sound_status` |
| Audio | `reachy_say` `reachy_play_sound` `reachy_volume` |
| Shared brain | `memory` `telegram` `dispatch` `prompts` `voice_say` `manage_messages` `manage_tools` |

Signatures: [tool reference](https://cagataycali.github.io/tiny-the-reachy/reference/tools/).

## Deploy

On a Reachy Mini Wireless, TINY runs on the robot's CM4 as user systemd units from
[`scripts/systemd/robot/`](scripts/systemd/robot/) (voice, telegram, thinker, wake) inside Pollen's venv;
the cockpit has its own unit in [`dashboard/deploy/`](dashboard/deploy/). On any Linux box next to a
daemon: `make install-bare-services`, or `make build && make up` for Docker Compose. Guides:
[Systemd](https://cagataycali.github.io/tiny-the-reachy/start/systemd/) ·
[On the robot](https://cagataycali.github.io/tiny-the-reachy/start/robot/) · [Docker](https://cagataycali.github.io/tiny-the-reachy/start/docker/)

## Safety

Experimental software moving real hardware — not a product. Keep the desk clear and watch it.
[Safety envelope →](https://cagataycali.github.io/tiny-the-reachy/guide/safety/)

- `reachy_look` / `reachy_body_turn` clamp head pitch/roll to ±40°, head yaw to ±180°, body yaw to
  ±160°. Clamps are not obstacle detection.
- The cockpit's STOP cancels running moves and the reel; it does not stop the thinker, tracking or
  turn-to-sound — disable those first.
- `reachy_motors("disabled")` drops holding torque; support the head.
- `make mute` and Telegram `/mute` set a memory flag the voice loop does not read yet.
  `reachy_volume("silent")` mutes the speaker only; to stop listening, stop the voice process.
- The agent has `shell` and can create tools at runtime — run it only for people you trust.

## License

MIT — see [LICENSE](LICENSE). Built on the
[Reachy Mini SDK](https://github.com/pollen-robotics/reachy_mini),
[Strands Agents](https://github.com/strands-agents) and [tiny.technology](https://tiny.technology).
Siblings: [Scout the Rover](https://github.com/cagataycali/scout-the-rover) ·
[NEON the G1](https://github.com/cagataycali/neon-the-g1).
