---
title: Troubleshooting
description: "Symptom → cause → command, for the eight things that actually go wrong: daemon unreachable, motors off, first-call hangs, no camera, silent voice, import-ok-but-nothing-runs, odd poses."
for: anyone staring at an error string
proof: robot
verified: 2026-09-21
---

# Troubleshooting

!!! abstract "In 10 seconds"
    - Every tool returns an error *string*, never a traceback — its first line names the layer: `connection refused on :8000` (daemon), `motors`, `media`, `voice`.
    - Check in order: daemon (`curl -s localhost:8000/api/daemon/status`) → motors → media → keys.
    - On the robot the units restart themselves; read *why* with `journalctl _SYSTEMD_USER_UNIT=tiny-voice.service -n 50` before touching anything.
    - Voice back-off: a *fatal* provider error doubles the delay 5 → 300 s; transient ones (DNS after reboot, busy audio device) retry in 5 s.

## Cannot connect to the daemon

```
reachy_* failed: connection refused on :8000
```

Wrong host, or no daemon.

- **Lite**: `REACHY_CONNECTION_MODE=auto` (localhost:8000)
- **Wireless**: `REACHY_HOST=reachy-mini.local`, `REACHY_CONNECTION_MODE=network`
- **No robot**: `make sim`

```bash
curl http://$REACHY_HOST:8000/api/daemon/status
```

## Motors will not move

Disabled or in gravity-comp:

```
> check state          # reachy_get_state → look at motor mode
> enable your motors   # reachy_motors('enabled')
```

## `reachy_express` hangs on first call

The emotion library is **downloaded live** the first time; later calls are cached. `reachy_list_emotions` warms it too.

## Camera returns nothing

The daemon owns the camera. If grabs conflict:

```bash
REACHY_MEDIA_BACKEND=no_media    # let reachy_camera grab transiently
REACHY_CAMERA_BACKEND=local      # backend used for transient grabs
```

## Voice persona is silent

```bash
make voice-status    # is it muted?
make unmute
```

Then `OPENAI_API_KEY` in `.env`. On the robot, read the unit before guessing:

```bash
journalctl _SYSTEMD_USER_UNIT=tiny-voice.service -n 50 --no-pager
```

| you see | it means | do |
|---|---|---|
| `Temporary failure in name resolution` | booted before DNS | nothing — retries in 5 s |
| `[Errno -9985] Device unavailable` | daemon still bringing its dmix pipeline up | nothing — retries in 5 s |
| `invalid_api_key` / `401` | the key in `.env` | fix it, `systemctl --user restart tiny-voice` |
| up, but you cannot interrupt it | XMOS `PP_NLATTENONOFF=1` (factory) mutes you while it speaks | `VOICE_XMOS_PARAMS` is re-applied at every start — check the board answered |

A mid-conversation restart takes ~90 s — the old session drains first.

## Everything imports but nothing runs

```bash
make test-tools     # passes → the problem is connectivity or credentials, not code
```

## It fell over / weird pose

```
> go home        # reachy_home — back to neutral
> go to sleep    # reachy_wake(sleep=True) — settle safely
```
