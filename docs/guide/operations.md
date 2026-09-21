---
title: Operations — keeping TINY alive
description: "The operational memory of the first days on the CM4: the 60-second health check, the incident log with root causes, live mitigations that need no reboot, measured budgets, and the demo checklist."
for: whoever is on call for the desk
proof: robot
verified: 2026-09-17
---

# Operations — keeping TINY alive

!!! abstract "In 10 seconds"
    - Run the health check first.
    - The daemon's fd limit and media release/acquire cycles caused every early outage; `restart`, never `stop`.
    - Before a demo: `demo on`, fds &lt; ~800. After: `demo off`.

## The 60-second health check

```bash
ssh reachy 'systemctl --user is-active tiny-wake tiny-tts tiny-voice tiny-telegram tiny-thinker reachy-dashboard reachy-tunnel; \
  cut -d" " -f1-3 /proc/loadavg; df -h / | tail -1; \
  P=$(pgrep -f "reachy_mini.daemon.app.main"); echo "daemon pid $P fds $(sudo ls /proc/$P/fd | wc -l) limit $(grep "Max open files" /proc/$P/limits | awk "{print \$4}")"'
curl -s $COCKPIT/api/health | jq '{daemon: .daemon, camera: .camera.fps, pressure: .pressure, stream: .stream}'
```

Healthy: seven `active`, load 3–4, 300–600 fds, `close_wait` 0.

```bash
journalctl _SYSTEMD_USER_UNIT=tiny-voice.service --since "10 min ago" -o cat        # journalctl --user finds nothing on the CM4
journalctl -u reachy-mini-daemon --since "5 min ago" -o cat | grep -oE '"(GET|POST) [^ ?]*' | sort | uniq -c | sort -rn   # who is hammering the daemon
```

## Incident log

| when (BST) | what you saw | root cause | fix |
|---|---|---|---|
| 09-16 23:00 | every persona *"Lost connection"* 12 min after a daemon restart | SDK client never reconnects | `get_mini()` rebuilds it |
| 09-17 03:05 | cockpit dark 2 min | `stop` + SIGKILL; uvicorn waits on MJPEG clients | `timeout_graceful_shutdown=2` |
| 09-17 05:29 | perception dead 10 min | **1024/1024 fds**, 614 CLOSE-WAIT — ~1300 req/min on fresh TCP; `tiny-mhs` crash-looping | one session + one WebSocket; `LimitNOFILE=65536`; watchdog; mhs gated |
| 09-17 06:20 | fds climbing ~1/s, 0 CLOSE-WAIT | `tiny-voice` crash-looped on a bad key, **releasing media every retry** — ~30 leaked unix sockets each | `prlimit` live; release once, back off (`3fc0e23`) |

**A persona that cannot start must not touch the daemon's media** — and watch fds, not CLOSE-WAIT.

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

| resource | idle | face tracking | camera | note |
|---|---|---|---|---|
| load (4 cores) | ~2.5 | +1.0–1.5 | +0.5 | `F` when the temperature pill is amber |
| daemon CPU | ~60 % | ~135 % | — | YuNet |
| daemon fds | 300–600 | — | — | +≈30 per release/acquire |
| requests to :8000 | ≈160/min | — | — | face poll is the largest |
| disk | 89 % | | | 1.5 GB free |

## Before a demo

1. `POST /api/control/demo {"on":true}` (`D`) — thinker off.
2. Health check; fds under ~800.
3. `POST /api/volume {"level":60}`.
4. After: `demo off` — the heartbeat feeds the Telegram photos.

## What we never do

- `git push` from the robot — the repo is public.
- Expose `:8000` — no auth.
- Poll the daemon from new code — read `robot.stream`.
- `pip install` on the CM4 without `df -h`.
