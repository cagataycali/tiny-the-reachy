---
title: Docker — laptop and Lite
description: "The three-persona compose stack for a laptop beside a Reachy Mini Lite or a dev box on the robot's network — not what the CM4 runs."
for: laptop + Lite owners · dev boxes
proof: code
verified: 2026-09-21
---

# Docker — laptop and Lite

!!! abstract "In 10 seconds"
    - `make build && make up` → three containers (`tiny-voice`, `tiny-telegram`, `tiny-thinker`) sharing one SQLite brain, host networking to the daemon.
    - The image is light: no DDS, no realsense — Reachy control is plain HTTP/WS to `:8000`.
    - `make install-compose-service` brings the stack up at boot.

!!! note "Not what the robot runs"
    The Wireless CM4 has **no Docker** and no room for it (disk 89 %). Compose is for a laptop next to a **Lite**, or a dev box pointed at the robot. The robot runs the personas bare-metal — [Systemd](systemd.md).

## Build and up

```bash
cp .env.example .env && $EDITOR .env
make build      # build the tiny image
make up         # docker compose up -d  → voice + telegram + thinker
```

## The three containers

| container | role |
|---|---|
| `tiny-voice` | always-on voice: local mic → speaker, head-wobble on speech |
| `tiny-telegram` | Telegram DM listener → one agent per message |
| `tiny-thinker` | 30 s heartbeat → photo + one expression + journal |

All three mount `.memory/mem.db` and reach the daemon at `REACHY_HOST`.

## Operate

```bash
make ps           # container status
make logs         # follow all logs
make logs-voice   # just the voice persona
make restart      # restart the whole stack
make down         # stop everything
```

## Live voice control

```bash
make mute         # silence the voice agent (persists in mem.db)
make unmute
make voice-status
```

## Boot on power-on

```bash
make install-compose-service   # user systemd unit → docker compose up -d at boot
```

