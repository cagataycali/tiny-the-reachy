---
title: Troubleshooting
description: "Symptom → cause → command, for the eight things that actually go wrong: daemon unreachable, motors off, first-call hangs, no camera, silent voice, import-ok-but-nothing-runs, odd poses."
for: anyone staring at an error string
proof: robot
verified: 2026-09-21
---

# Troubleshooting

!!! abstract "In 10 seconds"
    - Every tool returns an error *string*, never a traceback — the first line of it names the layer: `connection refused on :8000` (daemon), `motors` (asleep), `media` (camera), `voice` (key or audio device).
    - Check in this order: daemon (`curl -s localhost:8000/api/daemon/status`) → motors (`reachy_wake`) → media → keys.
    - On the robot the units restart themselves (`Restart=on-failure`); read *why* with `journalctl _SYSTEMD_USER_UNIT=tiny-voice.service -n 50` before touching anything.
    - Voice back-off: after a *fatal* provider error the retry delay doubles 5 → 300 s (`VOICE_RESTART_DELAY*`); transient errors (DNS after reboot, a busy audio device) retry in 5 s.

## Cannot connect to the daemon

```
reachy_* failed: connection refused on :8000
```

The daemon isn't up or you're pointed at the wrong host.

- **Lite**: daemon runs on your laptop → `REACHY_CONNECTION_MODE=auto` (localhost:8000)
- **Wireless**: daemon runs on the CM4 → `REACHY_HOST=reachy-mini.local` (or its IP), `REACHY_CONNECTION_MODE=network`
- **No robot**: `make sim` (`REACHY_USE_SIM=1`) spawns its own daemon

Verify the daemon directly:

```bash
curl http://$REACHY_HOST:8000/            # should return the daemon API
```

## Motors will not move

Check torque mode — motors may be disabled or in gravity-comp:

```
> check state          # reachy_get_state → look at motor mode
> enable your motors   # reachy_motors('enabled')
```

## `reachy_express` hangs on first call

The emotion library
(`pollen-robotics/reachy-mini-emotions-library`) is **downloaded live** the
first time. Give it a moment; subsequent calls are cached. `reachy_list_emotions`
warms it too.

## Camera returns nothing

The daemon owns the camera. If frame grabs conflict:

```bash
REACHY_MEDIA_BACKEND=no_media    # let reachy_camera grab transiently
REACHY_CAMERA_BACKEND=local      # backend used for transient grabs
```

## Voice persona is silent

```bash
make voice-status    # is it muted?
make unmute
```

Also confirm `OPENAI_API_KEY` (or your chosen `VOICE_PROVIDER`) is set in `.env`.

On the robot, read the unit before guessing:

```bash
journalctl _SYSTEMD_USER_UNIT=tiny-voice.service -n 50 --no-pager
```

| you see | it means | do |
|---|---|---|
| `Temporary failure in name resolution` | booted before DNS was up | nothing — transient, retries in 5 s (`voice_listener._is_fatal`) |
| `[Errno -9985] Device unavailable` | the daemon was still bringing its dmix pipeline up | nothing — transient, retries in 5 s |
| `invalid_api_key` / `401` | the key in `.env` | fix the key, `systemctl --user restart tiny-voice`; until then the retry delay doubles up to `VOICE_RESTART_DELAY_MAX` (300 s) |
| up, but you cannot interrupt it | XMOS `PP_NLATTENONOFF=1` (factory) mutes you while it speaks | `VOICE_XMOS_PARAMS` is re-applied at every start (`tools/xmos_audio.py`); check the board answered |

A mid-conversation restart takes ~90 s to hand the session over — the old one drains first.

## Everything imports but nothing runs

Run the smoke test — it isolates import/registration problems from hardware:

```bash
make test-tools
```

If that passes, the issue is connectivity or credentials, not code.

## It fell over / weird pose

```
> go home        # reachy_home — back to neutral
> go to sleep    # reachy_wake(sleep=True) — settle safely
```
