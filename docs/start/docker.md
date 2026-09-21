---
title: Docker — laptop and Lite
description: "The three-persona compose stack for a laptop beside a Reachy Mini Lite or a dev box on the robot's network — not what the CM4 runs."
for: laptop + Lite owners · dev boxes
proof: code
verified: 2026-09-21
---

# Docker — laptop and Lite

!!! abstract "In 10 seconds"
    - `make build && make up` → three containers (`tiny-voice`, `tiny-telegram`, `tiny-thinker`, `docker-compose.yml`) sharing one SQLite brain, host networking to the daemon.
    - The image is light: no DDS, no realsense — Reachy control is plain HTTP/WS to `:8000`.
    - The Wireless CM4 has **no Docker** (disk 89 %); it runs the same personas bare-metal under [systemd](systemd.md).
    - `make install-compose-service` makes the stack come up at boot on the laptop.

!!! note "Not what the robot runs"
    The Wireless CM4 has **no Docker** and no room for it (disk 89 %). Compose is for a laptop next to a
    Reachy Mini **Lite**, or a dev box pointed at the robot over the network. The robot itself runs the
    personas bare-metal — see [Systemd](systemd.md).

The recommended deploy: three always-on personas as containers, sharing one
SQLite brain, all connecting to the Reachy daemon over host networking. The
image is **light** — no DDS, no CycloneDDS, no librealsense build (unlike
neon), because Reachy control is pure HTTP/WS to the daemon.

## Build and up

```bash
cp .env.example .env && $EDITOR .env
make build      # build the tiny image
make up         # docker compose up -d  → voice + telegram + thinker
```

## The three containers

| container | role |
|---|---|
| `tiny-voice` | always-on bidirectional voice (local mic → speaker, head-wobble on speech) |
| `tiny-telegram` | Telegram DM listener → spawns a telegram-persona agent per message |
| `tiny-thinker` | 30s heartbeat → photo + one expression + telegram status + journal |

All three mount `.memory/mem.db` — the shared cross-persona brain — and reach
the daemon over host networking (`REACHY_HOST` from `.env`).

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

See [systemd](systemd.md) for the bare-metal alternative.
