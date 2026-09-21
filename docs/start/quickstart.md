---
title: Quickstart
description: "Clone, pick a model, point TINY at a daemon — real robot or MuJoCo — and get the first antenna wobble in three minutes."
for: anyone with a terminal · robot optional
proof: robot
verified: 2026-09-21
---

# Quickstart

!!! abstract "In 10 seconds"
    - `make venv && make run` talks to a Reachy Mini daemon on `:8000`; `make sim` spawns a MuJoCo one when you have no robot.
    - Default brain is Bedrock (`TINY_MODEL_ID=global.anthropic.claude-opus-4-8`, `tiny.py:25`); voice is OpenAI Realtime (`VOICE_PROVIDER=openai`, `voice_listener.py:19`).
    - Every gesture is clamped before it reaches the daemon, so the first commands below cannot hurt the robot.
    - Commands re-checked against `Makefile` and `.env.example` on 2026-09-21.

<div class="cards cards--3" markdown>

| mode | what runs where | when |
|---|---|---|
| **Lite** | daemon on your laptop over USB, TINY beside it | you own a Lite, or you develop tools → [connect](#3-connect-to-the-robot) |
| **Wireless** | daemon + TINY on the robot's CM4, as systemd units | the robot lives on a desk and should not need your laptop → [systemd](systemd.md) |
| **Simulation** | `REACHY_USE_SIM=1` spawns a headless MuJoCo daemon | no hardware, CI, or trying a new emotion safely → [docker](docker.md) |

</div>

## 1. Clone and run

```bash
git clone https://github.com/cagataycali/tiny-the-reachy.git
cd tiny-the-reachy
cp .env.example .env && $EDITOR .env   # fill in your keys (below)
make venv                              # .venv + deps
make run                               # REPL against the Reachy daemon
```

No hardware handy? Run against the MuJoCo simulator instead:

```bash
make sim        # REACHY_USE_SIM=1 — spawns a headless daemon, no robot
```

## 2. Pick a model

TINY runs on a Bedrock model by default. Provide Bedrock credentials before
`make run`:

```bash
export AWS_BEARER_TOKEN_BEDROCK=...                    # Bedrock bearer token (preferred)
export AWS_DEFAULT_REGION=us-west-2
export TINY_MODEL_ID=global.anthropic.claude-opus-4-8  # override the default
```

Voice uses OpenAI Realtime by default — set `OPENAI_API_KEY` for the voice
persona (or switch `VOICE_PROVIDER` to `nova_sonic` / `gemini`).

## 3. Connect to the robot

The **Reachy Mini daemon** owns the hardware and exposes an HTTP/WS API on
`:8000`. TINY is a pure client of it.

=== "Lite (USB → laptop)"

    ```bash
    REACHY_CONNECTION_MODE=auto     # daemon on localhost:8000
    ```

=== "Wireless (onboard CM4)"

    ```bash
    REACHY_HOST=reachy-mini.local   # or the robot's IP, e.g. 192.168.1.5
    REACHY_CONNECTION_MODE=network
    REACHY_PORT=8000
    ```

=== "Simulation (no hardware)"

    ```bash
    REACHY_USE_SIM=1                # MuJoCo, spawns its own daemon
    ```

## 4. Talk to it

<div class="terminal" markdown>
<span class="p">&gt;</span> check state

<span class="ok">reachy_state → head pitch/roll/yaw 0/0/0 · antennas 0/0 · body_yaw 0 · imu ok</span>

<span class="p">&gt;</span> show me you're happy to meet me

<span class="ok">reachy_express("cheerful1") · reachy_antennas(wiggle) — there is no "happy" in the library; TINY picks the closest of 81</span>
</div>

The REPL is a Strands agent with the same tools as the personas — [all 28, with signatures](../reference/tools/index.md).
`reachy_list_emotions` prints the recorded-move names the daemon actually has.

## Safe first commands

!!! tip "Green zone — all self-bounded, all clamped"
    `check state` · `wake up` · `look at me` · `wiggle your antennas` ·
    `nod` · `shake your head` · `spin around` · `show me happy` ·
    `what emotions do you know?` · `go home`

!!! note "Expression is the whole point"
    Reachy Mini has no arms or legs. Its personality is head + body + antennas
    + the recorded-emotion library. Ask it to *feel* something, not just *do*
    something — `be curious`, `look excited`, `act shy`.

## One-shot mode

```bash
make ask Q="say hi and wobble your antennas"
```

## On the real robot

The Wireless Reachy Mini runs all of this **on its own CM4** as systemd units — voice, Telegram, the
thinker, the cockpit and the tunnel — so nothing on your laptop needs to stay up.

[How TINY boots (systemd) →](systemd.md){ .md-button .md-button--primary }
[Deploying to the robot →](robot.md){ .md-button }
[Meet the four personas →](../showcase/personas.md){ .md-button }
