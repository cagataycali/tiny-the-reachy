# daemon reference

<span class="read-badge">⏱ 30s</span>

TINY never touches hardware directly — it's a pure client of the **Reachy Mini
daemon**, a FastAPI service that owns the robot and exposes an HTTP/WS API on
port `:8000`.

## where it runs

| variant | daemon host | connection mode |
|---|---|---|
| **Lite** (USB to laptop) | `localhost:8000` | `REACHY_CONNECTION_MODE=auto` |
| **Wireless** (onboard CM4) | `reachy-mini.local:8000` (or IP) | `REACHY_CONNECTION_MODE=network` |
| **Sim** (MuJoCo) | spawned locally | `REACHY_USE_SIM=1` |

## the cached client

All robot tools go through one cached singleton in `_reachy_common.py`:

```python
from ._reachy_common import get_mini
mini = get_mini()      # ReachyMini SDK client — connects once, reused everywhere
```

!!! danger "Never reconnect"
    Constructing a second `ReachyMini()` fights the daemon for control and
    causes flaky motion. Always go through `get_mini()`.

## verified SDK surface (1.9)

The daemon/SDK methods TINY's tools rely on:

```
goto_target · set_target · wake_up · goto_sleep
get_current_head_pose · get_current_joint_positions
enable_motors · disable_motors · enable_gravity_compensation
look_at_image · play_move · enable_wobbling
media.get_frame · media.play_sound · imu
RecordedMoves.list_moves()
```

## check it's alive

```bash
curl http://$REACHY_HOST:8000/     # returns the daemon's API surface
```

A live Wireless unit (from `LIVE_DEPLOY.md`) connects raw in ~0.7s and reads
head pose + antennas immediately.
