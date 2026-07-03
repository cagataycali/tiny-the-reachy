# troubleshooting

<span class="read-badge">⏱ 60s</span>

## can't connect to the daemon

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

## motors won't move

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

## camera returns nothing

The daemon owns the camera. If frame grabs conflict:

```bash
REACHY_MEDIA_BACKEND=no_media    # let reachy_camera grab transiently
REACHY_CAMERA_BACKEND=local      # backend used for transient grabs
```

## voice persona is silent

```bash
make voice-status    # is it muted?
make unmute
```

Also confirm `OPENAI_API_KEY` (or your chosen `VOICE_PROVIDER`) is set in `.env`.

## everything imports but nothing runs

Run the smoke test — it isolates import/registration problems from hardware:

```bash
make test-tools
```

If that passes, the issue is connectivity or credentials, not code.

## it fell over / weird pose

```
> go home        # reachy_home — back to neutral
> go to sleep    # reachy_wake(sleep=True) — settle safely
```
