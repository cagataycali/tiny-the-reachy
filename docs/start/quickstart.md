---
title: Quickstart
description: "Clone, pick a model, point TINY at a daemon — real robot or MuJoCo — and get the first antenna wobble in three minutes."
for: anyone with a terminal · robot optional
proof: robot
verified: 2026-09-21
---

# Quickstart

!!! abstract "In 10 seconds"
    - `make venv && make run` talks to a daemon on `:8000`; `make sim` spawns MuJoCo instead.
    - Default brain: Bedrock (`TINY_MODEL_ID`); voice: OpenAI Realtime.
    - Every gesture is clamped — nothing here can hurt the robot.

<div class="cards cards--3" markdown>

| mode | what runs where | when |
|---|---|---|
| **Lite** | daemon on your laptop over USB, TINY beside it | developing tools |
| **Wireless** | daemon + TINY on the CM4 | a robot on a desk → [systemd](systemd.md) |
| **Simulation** | `REACHY_USE_SIM=1`, headless MuJoCo | no hardware, CI → [docker](docker.md) |

</div>

## 1. Clone and run

```bash
git clone https://github.com/cagataycali/tiny-the-reachy.git
cd tiny-the-reachy
cp .env.example .env && $EDITOR .env   # fill in your keys (below)
make venv                              # .venv + deps
make run                               # REPL against the Reachy daemon
```

```bash
make sim        # no robot: REACHY_USE_SIM=1 spawns a headless MuJoCo daemon
```

## 2. Pick a model

```bash
export AWS_BEARER_TOKEN_BEDROCK=...                    # Bedrock bearer token (preferred)
export AWS_DEFAULT_REGION=us-west-2
export TINY_MODEL_ID=global.anthropic.claude-opus-4-8  # override the default
```

Voice: `OPENAI_API_KEY`.

## 3. Connect

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

<span class="ok">reachy_express("cheerful1") · reachy_antennas(wiggle) — the closest of 81 moves to "happy"</span>
</div>

Same tools as the personas — [all 28](../reference/tools/index.md).

!!! tip "Safe first commands"
    `check state` · `wake up` · `look at me` · `wiggle your antennas` · `nod` · `spin around` · `go home`

!!! note "Expression is the whole point"
    Ask it to *feel* something, not *do* something: `be curious`, `act shy`.

## One-shot mode

```bash
make ask Q="say hi and wobble your antennas"
```

## On the real robot

[How TINY boots (systemd) →](systemd.md){ .md-button .md-button--primary }
[Deploying to the robot →](robot.md){ .md-button }
[Meet the personas →](../showcase/personas.md){ .md-button }
