# docker

<span class="read-badge">⏱ 90s · full stack</span>

The recommended deploy: three always-on personas as containers, sharing one
SQLite brain, all connecting to the Reachy daemon over host networking. The
image is **light** — no DDS, no CycloneDDS, no librealsense build (unlike
neon), because Reachy control is pure HTTP/WS to the daemon.

## build & up

```bash
cp .env.example .env && $EDITOR .env
make build      # build the tiny image
make up         # docker compose up -d  → voice + telegram + thinker
```

## the three containers

| container | role |
|---|---|
| `tiny-voice` | always-on bidirectional voice (local mic → speaker, head-wobble on speech) |
| `tiny-telegram` | Telegram DM listener → spawns a telegram-persona agent per message |
| `tiny-thinker` | 30s heartbeat → photo + one expression + telegram status + journal |

All three mount `.memory/mem.db` — the shared cross-persona brain — and reach
the daemon over host networking (`REACHY_HOST` from `.env`).

## operate

```bash
make ps           # container status
make logs         # follow all logs
make logs-voice   # just the voice persona
make restart      # restart the whole stack
make down         # stop everything
```

## live voice control

```bash
make mute         # silence the voice agent (persists in mem.db)
make unmute
make voice-status
```

## boot on power-on

```bash
make install-compose-service   # user systemd unit → docker compose up -d at boot
```

See [systemd](systemd.md) for the bare-metal alternative.
