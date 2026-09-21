---
title: Operations — keeping TINY alive
description: "The operational memory of the first days on the CM4: the 60-second health check, the incident log with root causes, live mitigations that need no reboot, measured budgets, and the demo checklist."
for: whoever is on call for the desk
proof: robot
verified: 2026-09-17
---

# Operations

!!! abstract "In 10 seconds"
    - Health check first. `restart`, never `stop`.
    - The daemon's fd limit and media release cycles caused every early outage.
    - Before a demo: `demo on`, fds &lt; ~800.

## Health check

```bash
ssh reachy 'systemctl --user is-active tiny-wake tiny-tts tiny-voice tiny-telegram tiny-thinker reachy-dashboard reachy-tunnel; \
  cut -d" " -f1-3 /proc/loadavg; df -h / | tail -1; \
  P=$(pgrep -f "reachy_mini.daemon.app.main"); echo "daemon pid $P fds $(sudo ls /proc/$P/fd | wc -l) limit $(grep "Max open files" /proc/$P/limits | awk "{print \$4}")"'
curl -s $COCKPIT/api/health | jq '{daemon: .daemon, camera: .camera.fps, pressure: .pressure, stream: .stream}'
```

Healthy: seven `active`, load 3–4, 300–600 fds.

```bash
journalctl _SYSTEMD_USER_UNIT=tiny-voice.service --since "10 min ago" -o cat        # journalctl --user finds nothing on the CM4
journalctl -u reachy-mini-daemon --since "5 min ago" -o cat | grep -oE '"(GET|POST) [^ ?]*' | sort | uniq -c | sort -rn   # who is hammering the daemon
```

## Incident log

| when | seen | cause | fix |
|---|---|---|---|
| 09-16 23:00 | personas *"Lost connection"* 12 min | SDK client never reconnects | `get_mini()` rebuilds it |
| 09-17 03:05 | cockpit dark 2 min | `stop`; uvicorn waits on MJPEG clients | `timeout_graceful_shutdown=2` |
| 09-17 05:29 | perception dead 10 min | **1024/1024 fds**, 614 CLOSE-WAIT — ~1300 req/min | one WebSocket; `LimitNOFILE=65536`; watchdog |
| 09-17 06:20 | fds climbing ~1/s | `tiny-voice` crash-looped, **releasing media every retry** | release once, back off |

**A persona that cannot start must not touch the daemon's media.**

## Live mitigations

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
| load (4 cores) | ~2.5 | +1.0–1.5 | +0.5 | `F` when the temperature pill goes amber |
| daemon CPU | ~60 % | ~135 % | — | YuNet |
| daemon fds | 300–600 | — | — | +≈30 per release/acquire |
| requests to :8000 | ≈160/min | — | — | face poll leads |
| disk | 89 % | | | 1.5 GB free |

## Before a demo

1. `demo on` (`D`) — thinker off.
2. Health check; fds under ~800.
3. Volume 60.
4. After: `demo off`.

## What we never do

- `git push` from the robot.
- Expose `:8000` — no auth.
- Poll the daemon — read `robot.stream`.
- `pip install` without `df -h`.
