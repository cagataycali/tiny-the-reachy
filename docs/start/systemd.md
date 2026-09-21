---
title: Systemd — how TINY boots
description: "One system unit, one timer and eight user units on the CM4 — the inventory as installed, and the lessons each unit encodes."
for: whoever keeps the robot alive
proof: robot
verified: 2026-09-17
---

# Systemd — how TINY boots

!!! abstract "In 10 seconds"
    - Pollen's `reachy-mini-daemon` (system unit, `:8000`) owns the hardware and boots **asleep**; `tiny-wake` energises the motors 8 s later and exits.
    - Eight `pollen` user units survive reboots via linger: wake · tts · voice · telegram · thinker · dashboard (`:8097`) · tunnel · mhs (gated).
    - `restart`, never `stop`, during a demo — a stopped unit does not come back.
    - `make install-bare-services` installs the three-persona subset anywhere (`scripts/systemd/robot/` = the CM4 variants).

```mermaid
flowchart TD
  P["power on · Debian 13 · CM4"] --> DAE["reachy-mini-daemon.service (system)<br/>launcher.sh → :8000 · starts ASLEEP"]
  DAE --> WD["reachy-daemon-watchdog.timer<br/>every 30 s → restart after 3 missed /api/daemon/status"]
  P --> L["linger=yes → default.target for pollen"]
  L --> WAKE["tiny-wake · sleep 8 → enable_motors + wake_up, os._exit"]
  L --> TTS["tiny-tts · Piper :5002"]
  L --> PER["tiny-voice · tiny-telegram · tiny-thinker"]
  L --> DASH["reachy-dashboard :8097"] --> TUN["reachy-tunnel · cloudflared"]
  L --> MHS["tiny-mhs · zenoh (gated)"]
  DAE -. After= .-> WAKE & PER & DASH
```

## The units, as installed (2026-09-17)

| unit | scope | why it exists |
|---|---|---|
| `reachy-mini-daemon` | system | Pollen's daemon — motors, camera, audio, `:8000`. Drop-in `LimitNOFILE=65536` (it hit 1024 — [Perception](../PERCEPTION.md)) |
| `reachy-daemon-watchdog.timer` | system | every 30 s from 180 s after boot; restarts the daemon after three failed `GET /api/daemon/status` |
| `tiny-wake` | user, oneshot | energises the motors once, **hard-exits** so no SDK socket lingers. **Boot volume floor**: `alsa-state` persists the mixer, so a robot unplugged while silent boots deaf — volume < `REACHY_BOOT_VOLUME_MIN` (60) is raised |
| `tiny-tts` | user | offline Piper `en_US-lessac-medium` (~2.6 s/sentence) for the text personas and **Say**; own venv |
| `tiny-voice` · `tiny-telegram` · `tiny-thinker` | user | the personas, `Restart=on-failure`. Demo mode stops/starts exactly `tiny-thinker` |
| `reachy-dashboard` | user | the cockpit: `Restart=always`, `Nice=5`, `TimeoutStopSec=8`, `KillMode=mixed`; env = repo `.env` + `~/.reachy-dashboard.env` |
| `reachy-tunnel` | user | named Cloudflare tunnel → `http://127.0.0.1:8097`, everything else `404` |
| `tiny-mhs` | user, gated | zenoh mount; drop-in `broker-gate.conf` runs `nc -z` first — sits in *activating (auto-restart)* off-site, by design |

Voice, telegram, thinker, dashboard carry a `tiny-mcp.conf` drop-in — the [fleet token](../MCP.md). Remove it; nothing else changes.

!!! warning "Lessons the units encode"
    - **`After=` is not enough.** The daemon answers HTTP seconds before the motors are ready; hence sleep 8 + 20 retries.
    - **Never `stop reachy-dashboard` in a demo — `restart`.** uvicorn waited on open MJPEG clients: ~90 s before `timeout_graceful_shutdown=2`.
    - **Every persona restart used to kill the camera.** A `no_media` SDK client releases the daemon's media; the dashboard re-acquires within a second.
    - **A dead SDK client stays dead.** After a daemon restart every persona said *"Lost connection with the server"* for 12 minutes — until `get_mini()` learned to rebuild a client whose `_is_alive` is false.

## Day-to-day

```bash
ssh reachy                                      # pollen@reachy-mini.local
systemctl --user list-units 'tiny-*' 'reachy-*'
systemctl --user restart tiny-voice             # after .env or a prompt
systemctl --user restart reachy-dashboard       # after dashboard/*.py (frontend: no restart)
journalctl _SYSTEMD_USER_UNIT=tiny-thinker.service -f   # journalctl --user finds no files here
curl -s localhost:8097/api/health | jq .pressure
sudo systemctl restart reachy-mini-daemon       # last resort; personas reconnect
```

No Docker on the CM4 — `docker-compose.yml` is for a laptop next to a Lite ([Docker](docker.md)).

## The repo way

```bash
make venv                     # .venv + requirements
make install-bare-services    # scripts/systemd/tiny-{voice,telegram,thinker}.service → ~/.config/systemd/user, enable-linger, enable --now
make service-status
```

!!! tip "Linger"
    `loginctl show-user $USER -p Linger` must say `yes`, or the units stop with the last SSH session — which looks exactly like "the robot forgot everything overnight".
