# Perception — face tracking · turn to sound · daemon pressure

*(2026-09-17, reachy-mini daemon 1.10.0, `dashboard/`)*

TINY's head is steered by three cooperating layers, all owned by the dashboard process on the CM4 and all reading
**one** daemon state WebSocket (`dashboard/daemonlink.py`):

| layer | source | module | default | switch |
|---|---|---|---|---|
| **face tracking** | daemon YuNet (`/api/media/tracking/*`) | `dashboard/tracking.py` | ON at boot (`REACHY_TRACK_AUTOSTART=1`), re-enabled after a daemon restart | 👁 pill / `F` · `POST /api/tracking` · tool `head_tracking()` |
| **turn to sound** | ReSpeaker DoA in every state frame (`doa`) | `dashboard/doa.py` | ON (`REACHY_DOA_TURN=1`) | 🔊 pill / `K` · `POST /api/doa` · tool `turn_to_sound()` |
| **IMU** (lifted / tilted) | daemon `imu` when present (Wireless only) | state passthrough → `state.imu` | badge on the twin | — |

Priority when they disagree: an explicit **look / emotion / say** holds the tracker and blocks DoA turns; a **fresh
face lock** (< 1.5 s) blocks DoA turns; DoA only acts when nobody is in view and nothing else is moving the head.

## Face tracking (daemon edition)

The daemon runs the detector on its own camera socket, so the **daemon must own the sensor** — the dashboard camera
uses the `ipc` backend (reads the daemon's GStreamer feed, 10 fps) and re-acquires media when an SDK client releases
it. The dashboard only toggles weight: `1` follow, `0` paused (holds), `disable` off.

* `ts: null` from `/api/media/tracking/face` means the detector is **off or paused** (weight 0 clears the aim). The
  dashboard treats it as a lost daemon only while it expects weight 1 with no holds, then re-enables (status
  `reasserts`). A daemon restart is also caught by the state stream reconnecting.
* Poll rate 2 Hz (`REACHY_TRACK_POLL_HZ`) — it used to be 5 Hz and was part of the EMFILE incident below.
* Cost: ~+1.0–1.5 load on the CM4 with tracking on. Turn it off for long unattended runs if the temperature pill goes
  amber.

Details: [FACE-TRACKING.md](FACE-TRACKING.md).

## Turn to sound (DoA)

Pollen's convention (`reachy_mini/media/audio_doa.py`): `angle` in radians, **0 = left, π/2 = front/back, π = right**.
A linear 4-mic array cannot tell front from back, so the angle is a left/right yaw delta:
`delta = SIGN · (π/2 − angle)` (`REACHY_DOA_SIGN=1` — confirmed by the owner speaking from TINY's left).

A turn fires when **all** hold:

1. `speech_detected` on ≥ 6 consecutive frames (10 Hz) whose angles agree within ±12°;
2. the reading is not a **rail** (within 3° of 0 or π — that is what the array reports for TINY's own speaker and
   for "no estimate");
3. TINY is **not speaking** (any `speaking` hold, plus a 1.5 s tail — remembered even when no face is locked, so the
   robot never chases its own voice);
4. no fresh face lock, no tracker hold, no move in flight, not lifted, ≥ 3 s since the last turn;
5. |delta| ≥ 10°;
6. **windup guard**: a same-direction turn within 10 s whose bearing did not shrink by 40 % is refused (the sound
   moved with the head → not a person). Version 1 without this wound the body to −143° in two minutes.

Then one `goto`: head yaw toward the sound up to ±45°, the body carries the rest up to ±60°, pitch kept, 0.7 s.
After that the face tracker takes over. `GET /api/doa` shows `why` (the rule that is currently blocking), `turns`,
`windups`, and `calib` — a live cross-check of the DoA side against the tracked face's `x` sign when both fire
(`suggested_sign` after 10 samples; own-voice frames excluded).

`REACHY_DOA_FRAME=head` (default) adds the delta to the current head yaw (mics move with the head); `body` treats
it as an absolute body-frame bearing. Every threshold is an env var (`REACHY_DOA_*`, see
[reference/env.md](reference/env.md)).

## Fields the cockpit consumes

From `GET /api/state` / WS `{type:"state"}` (all optional; the UI renders nothing when absent):

```jsonc
"tracking": {"enabled", "paused", "holds", "detected", "x", "y", "roll", "weight", "available", "error", "face_age_s", "reasserts"},
"doa":      {"angle": 1.57, "speech_detected": true},        // rad, Pollen convention → twin DoaArc
"doa_turn": {"enabled", "armed", "speech", "angle_deg", "delta_deg", "turns", "windups", "why", "sign", "calib": {...}},
"imu":      {"lifted"|"picked_up", "tilted"},                 // badge on the twin
"pressure": {"pid", "fds", "fd_limit", "close_wait", "established", "warn"},
"stream":   {"connected", "hz", "frames", "reconnects", "age_s", "error"},
"state_age_s": 0.04
```

WS events: `{type:"tracking", …}` on change, `{type:"doa", …}` on change / after a turn.

## Daemon pressure (the 05:29 BST EMFILE incident)

The daemon hit 1024/1024 fds with 614 sockets on :8000 in CLOSE-WAIT; camera, tracking and DoA died for 10 min.
Cause: the dashboard made ~1300 requests/min on fresh TCP connections (state/full + move/running at 15 Hz, face at
5 Hz), while `tiny-mhs` crash-looped every 40 s and each start built a `ReachyMini(no_media)` client — which in SDK
1.10 POSTs `/api/media/release` — so the daemon dropped its media pipeline every 40 s too.

Now: one keep-alive `requests.Session`, one `/api/state/ws/full` WebSocket shared by every consumer, `move/running`
only while a move can be in flight, face at 2 Hz → **≈160 requests/min over 3–5 persistent connections, 0
CLOSE-WAIT over 15 minutes**. `/api/health` and the cockpit carry the gauge (⚠ pill when fds > 60 % of the limit or
≥ 50 CLOSE-WAIT; telemetry strip shows `fds/limit · cw · ws|poll`). On the robot, a systemd timer
(`reachy-daemon-watchdog`, every 30 s) restarts the daemon after three missed `/api/daemon/status`, and
`LimitNOFILE=65536` applies at its next restart. `tiny-mhs` is gated on the venue broker being reachable.

A second pressure incident (06:20–07:00 BST the same day) came from the other direction: a persona that could not
start (`tiny-voice`, bad key) POSTed `/api/media/release` on every retry, and each release rebuilt the daemon's
media pipeline and leaked ≈30 unnamed unix sockets — fds 556 → 879 in 35 minutes with 0 CLOSE-WAIT, so the
CLOSE-WAIT gauge alone was blind to it. `voice_listener` now releases media once and backs off exponentially;
the fd gauge is the one to watch. Timeline and live mitigation in [Operations](guide/operations.md).

Rule of thumb for anything new on the CM4: **read from `robot.stream`, never poll the daemon yourself, and never
release media from a retry loop.**
