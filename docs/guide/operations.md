# Operations — keeping TINY alive

<span class="read-badge">⏱ 6 min · every number below was measured on the CM4</span>

The robot is a 4-core CM4 with 4 GB of RAM, a 14 GB SD card that is 89 % full and one process —
Pollen's daemon — that owns every sensor and motor. Everything we run competes with it. This page is the
operational memory of the first two days: what broke, why, how we saw it, and what to type.

## The 60-second health check

```bash
ssh reachy 'systemctl --user is-active tiny-wake tiny-tts tiny-voice tiny-telegram tiny-thinker reachy-dashboard reachy-tunnel; \
  cut -d" " -f1-3 /proc/loadavg; df -h / | tail -1; \
  P=$(pgrep -f "reachy_mini.daemon.app.main"); echo "daemon pid $P fds $(sudo ls /proc/$P/fd | wc -l) limit $(grep "Max open files" /proc/$P/limits | awk "{print \$4}")"'
curl -s https://reachy.cagatay.my/api/health | jq '{daemon: .daemon, camera: .camera.fps, pressure: .pressure, stream: .stream}'
```

Healthy on 2026-09-17: seven `active`, load 3–4, daemon ≈ 300–600 fds with limit 65536, camera 10 fps,
`pressure.close_wait` 0, `stream.connected` true at 10 Hz.

!!! tip "Reading the logs"
    `journalctl --user` says *No journal files were found* on the CM4 — but the **system** journal
    does hold the user units. This works:

    ```bash
    journalctl _SYSTEMD_USER_UNIT=tiny-voice.service --since "10 min ago" -o cat
    journalctl -u reachy-mini-daemon --since "5 min ago" -o cat | grep -oE '"(GET|POST) [^ ?]*' | sort | uniq -c | sort -rn
    ```

    The second line is the daemon's access log by endpoint — the fastest way to see who is hammering it.

## Incident log

| when (BST) | what you saw | root cause | fix |
|---|---|---|---|
| 09-16 ~23:00 | every persona: *"Lost connection with the server"* for 12 min after a daemon restart | SDK client object never reconnects; `client._is_alive` stays False | `tools/_reachy_common.get_mini()` rebuilds a dead client |
| 09-17 03:05 | cockpit dark for 2 min | `systemctl stop reachy-dashboard` + `TimeoutStopSec=8` SIGKILL; uvicorn waits on MJPEG clients, a *stop* job never auto-restarts | `timeout_graceful_shutdown=2`; only ever `restart` |
| 09-17 05:29 | camera, tracking and DoA dead 10 min; daemon at 109 % CPU | daemon hit **1024/1024 fds**: 614 sockets on :8000 in CLOSE-WAIT — dashboard made ~1300 req/min on fresh TCP connections, `tiny-mhs` crash-looped every 40 s releasing media | one keep-alive session + one shared state WebSocket (≈160 req/min, 0 CLOSE-WAIT); `LimitNOFILE=65536` drop-in; watchdog timer; mhs gated on its broker |
| 09-17 06:20–07:00 | daemon fds climbing ~1/s (556 → 879), load 6, voice persona "up" every 5–80 s | `tiny-voice` crash-looped on `invalid_api_key`; **every attempt POSTed `/api/media/release`**, each release rebuilt the daemon's GStreamer/WebRTC pipeline (21 releases, 18 acquires in 5 min) and leaked ~30 unnamed unix stream sockets per rebuild; the drop-in limit had not applied because the daemon predates it | `sudo prlimit --pid <daemon> --nofile=65536:524288` live (no restart); key replaced; `voice_listener` no longer releases media on retry and backs off exponentially (`3fc0e23`) |

The fourth row is the important lesson: **a persona that cannot start must not touch the daemon's media.**
Every `/api/media/release` costs the daemon a full pipeline rebuild — and, in 1.10.0, some sockets it never
gives back. The dashboard's ⚠ pill (fds > 60 % of the limit or ≥ 50 CLOSE-WAIT) is the early warning; the
daemon access log tells you who.

## Live mitigations (no reboot)

```bash
# daemon near its fd limit and you cannot restart it mid-demo
P=$(pgrep -f "reachy_mini.daemon.app.main"); sudo prlimit --pid $P --nofile=65536:524288

# a persona is crash-looping: stop it, read why, fix, restart
systemctl --user stop tiny-voice
journalctl _SYSTEMD_USER_UNIT=tiny-voice.service -n 40 -o cat
systemctl --user restart tiny-voice

# daemon lost the camera (every persona restart used to do this)
curl -s -X POST localhost:8000/api/media/acquire      # the dashboard does this itself within ~1 s

# thinker gestures on top of a live demo
curl -s -X POST -H "Authorization: Bearer $REACHY_TOKEN" -H 'content-type: application/json' \
     https://reachy.cagatay.my/api/control/demo -d '{"on":true}'    # = systemctl --user stop tiny-thinker

# daemon truly wedged
sudo systemctl restart reachy-mini-daemon                   # personas reconnect on their own now
```

## Budgets

| resource | idle | with face tracking | with dashboard camera | comment |
|---|---|---|---|---|
| load average (4 cores) | ~2.5 | +1.0–1.5 | +0.5 | tracking is ON by default (`REACHY_TRACK_AUTOSTART=1`); turn it off (`F`) if the temperature pill goes amber |
| daemon CPU | ~60 % | ~135 % | — | YuNet runs inside the daemon |
| daemon fds | 300–600 | — | — | +≈30 leaked per media release/acquire cycle |
| requests to :8000 | ≈160/min | — | — | face poll 2 Hz is the largest single caller (541 per 5 min) |
| disk | 89 % | | | 1.5 GB free — no new venvs, `apt clean` before anything |

## Before a demo

1. `POST /api/control/demo {"on":true}` (or `D` in the cockpit) — thinker off.
2. Health check above; `pressure.fds` under ~800 or raise the limit live.
3. Face tracking on, turn-to-sound on (🔊 pill) — both default on.
4. Phone: stop Telegram banners — that *is* the thinker; step 1 covers it.
5. Volume: say "TINY, normal volume" or `POST /api/volume {"level":60}`.
6. After: `demo off` — the heartbeat is what keeps the Telegram photo stream alive.

## What we never do

- `git push` from the robot or copy `.env` anywhere — the repo is public.
- Expose `:8000` — the daemon has no auth.
- `systemctl stop` the dashboard during a demo — `restart`.
- Poll the daemon from new code — read `robot.stream` inside the dashboard, or `/api/state` from outside.
- Prune, purge or `pip install` on the CM4 without `df -h` first.
