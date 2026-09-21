---
title: Operations — keeping TINY alive
description: "The operational memory of the first days on the CM4: the 60-second health check, the incident log with root causes, live mitigations that need no reboot, measured budgets, and the demo checklist."
for: whoever is on call for the desk
proof: robot
verified: 2026-09-17
---

# Operations — keeping TINY alive

!!! abstract "In 10 seconds"
    - One `ssh reachy` line + one `curl $COCKPIT/api/health` tell you unit states, load, disk and the daemon's fd pressure — run it first.
    - The daemon's fd limit (1024 → 65536) and media release/acquire cycles caused every early outage; `restart`, never `stop`, the dashboard.
    - Budgets on the CM4: load ~2.5 idle, +1.0–1.5 with face tracking; daemon ~60 % CPU idle, ~135 % tracking; disk 89 % — no new venvs.
    - Before a demo: thinker off (`demo on`), fds < ~800, tracking + turn-to-sound on, volume 60. After: `demo off`.

Four cores, 4 GB, a 14 GB card 89 % full, and one process — Pollen's daemon — that owns every sensor and motor. Everything we run competes with it.

## The 60-second health check

```bash
ssh reachy 'systemctl --user is-active tiny-wake tiny-tts tiny-voice tiny-telegram tiny-thinker reachy-dashboard reachy-tunnel; \
  cut -d" " -f1-3 /proc/loadavg; df -h / | tail -1; \
  P=$(pgrep -f "reachy_mini.daemon.app.main"); echo "daemon pid $P fds $(sudo ls /proc/$P/fd | wc -l) limit $(grep "Max open files" /proc/$P/limits | awk "{print \$4}")"'
curl -s $COCKPIT/api/health | jq '{daemon: .daemon, camera: .camera.fps, pressure: .pressure, stream: .stream}'
```

Healthy (2026-09-17): seven `active`, load 3–4, daemon 300–600 fds of 65536, camera 10 fps, `close_wait` 0, `stream.connected` at 10 Hz.

```bash
journalctl _SYSTEMD_USER_UNIT=tiny-voice.service --since "10 min ago" -o cat        # journalctl --user finds nothing on the CM4
journalctl -u reachy-mini-daemon --since "5 min ago" -o cat | grep -oE '"(GET|POST) [^ ?]*' | sort | uniq -c | sort -rn   # who is hammering the daemon
```

## Incident log

| when (BST) | what you saw | root cause | fix |
|---|---|---|---|
| 09-16 ~23:00 | every persona *"Lost connection with the server"* for 12 min after a daemon restart | SDK client never reconnects; `_is_alive` stays False | `get_mini()` rebuilds a dead client |
| 09-17 03:05 | cockpit dark 2 min | `systemctl stop` + SIGKILL at 8 s; uvicorn waits on MJPEG clients, a *stop* job never auto-restarts | `timeout_graceful_shutdown=2`; only ever `restart` |
| 09-17 05:29 | camera, tracking, DoA dead 10 min; daemon 109 % CPU | **1024/1024 fds**: 614 CLOSE-WAIT sockets — dashboard ~1300 req/min on fresh TCP, `tiny-mhs` crash-looping every 40 s releasing media | one keep-alive session + one state WebSocket (≈160 req/min); `LimitNOFILE=65536`; watchdog; mhs gated |
| 09-17 06:20 | fds climbing ~1/s, load 6, voice "up" every 5–80 s | `tiny-voice` crash-looped on `invalid_api_key`, **every attempt POSTed `/api/media/release`** — each one rebuilt the daemon's pipeline and leaked ~30 unix sockets | `prlimit` live; key replaced; `voice_listener` no longer releases media on retry, backs off (`3fc0e23`) |

The lesson of the fourth row: **a persona that cannot start must not touch the daemon's media.** The ⚠ pill (fds > 60 % or ≥ 50 CLOSE-WAIT) is the early warning; the access log says who.

## Live mitigations (no reboot)

```bash
P=$(pgrep -f "reachy_mini.daemon.app.main"); sudo prlimit --pid $P --nofile=65536:524288   # fd limit, mid-demo
systemctl --user stop tiny-voice && journalctl _SYSTEMD_USER_UNIT=tiny-voice.service -n 40 -o cat   # crash loop: read, fix, restart
curl -s -X POST localhost:8000/api/media/acquire                                             # camera lost (dashboard does this itself)
curl -s -X POST -H "Authorization: Bearer $REACHY_TOKEN" -H 'content-type: application/json' \
     $COCKPIT/api/control/demo -d '{"on":true}'                                             # = systemctl --user stop tiny-thinker
sudo systemctl restart reachy-mini-daemon                                                   # truly wedged; personas reconnect
```

## Budgets

| resource | idle | face tracking | dashboard camera | note |
|---|---|---|---|---|
| load (4 cores) | ~2.5 | +1.0–1.5 | +0.5 | tracking ON by default; `F` when the temperature pill goes amber |
| daemon CPU | ~60 % | ~135 % | — | YuNet runs inside the daemon |
| daemon fds | 300–600 | — | — | +≈30 leaked per release/acquire cycle |
| requests to :8000 | ≈160/min | — | — | the 2 Hz face poll is the largest caller |
| disk | 89 % | | | 1.5 GB free |

## Before a demo

1. `POST /api/control/demo {"on":true}` (`D`) — thinker off; that also stops the Telegram photo banners.
2. Health check; `pressure.fds` under ~800 or raise the limit live.
3. Tracking and turn-to-sound on — both default on.
4. Volume: *"TINY, normal volume"* or `POST /api/volume {"level":60}`.
5. After: `demo off` — the heartbeat keeps the Telegram photo stream alive.

## What we never do

- `git push` from the robot or copy `.env` anywhere — the repo is public.
- Expose `:8000` — no auth.
- `stop` the dashboard during a demo — `restart`.
- Poll the daemon from new code — read `robot.stream`, or `/api/state` from outside.
- `pip install` on the CM4 without `df -h` first.
