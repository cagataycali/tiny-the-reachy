---
title: Safety envelope
description: "What TINY clamps before a value reaches the daemon, what it deliberately leaves to the SDK, and where each limit lives in the code — read from tools/_reachy_common.py, not remembered."
for: anyone writing a motion tool or a prompt that moves the head
proof: code
verified: 2026-09-21
---

# Safety envelope

!!! abstract "In 10 seconds"
    - Head pitch/roll ±40°, yaw ±180°, body yaw ±160° — `clamp()`ed **before** the daemon.
    - Antennas, head translation, recorded emotions: bounded by daemon and SDK.
    - `MAX_YAW_DELTA = 65°` is declared but **no tool enforces it**.

## The envelope

<div class="filterable" data-id="limit" data-placeholder="pitch, body, antenna…" markdown>

| value | limit | enforced by | where |
|---|---|---|---|
| head pitch | ±40° | TINY `clamp()`, then SDK | `_reachy_common.py:32` · `reachy_motion.py:62` |
| head roll | ±40° | TINY, then SDK | `:33` · `:63` |
| head yaw | ±180° | TINY, then SDK | `:34` · `:64` |
| body yaw | ±160° | TINY, then SDK | `:35` · `:66,118` |
| head − body yaw delta | 65° | daemon — declared, unused | `:36` |
| antennas | ~±90° | daemon / SDK | radians pass through |
| head translation | ~±20 mm | daemon / SDK | `create_head_pose` |
| move duration | ≥ 0.1 s | TINY `max(0.1, duration)` | `goto_target` |
| recorded emotions | the daemon's library | daemon | only a *name* travels |

</div>

## Where it is enforced

```python
# tools/_reachy_common.py:32-36 — verbatim
LIM_HEAD_PITCH = (-40.0, 40.0)
LIM_HEAD_ROLL = (-40.0, 40.0)
LIM_HEAD_YAW = (-180.0, 180.0)
LIM_BODY_YAW = (-160.0, 160.0)
MAX_YAW_DELTA = 65.0

# tools/_reachy_common.py:103
def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
```

```python
# tools/reachy_motion.py:62-66 — the first thing reachy_look does
pitch = clamp(pitch, *LIM_HEAD_PITCH)
roll = clamp(roll, *LIM_HEAD_ROLL)
yaw = clamp(yaw, *LIM_HEAD_YAW)
if body_yaw is not None:
    body_yaw = clamp(body_yaw, *LIM_BODY_YAW)
```

The SDK clamps again; the daemon rejects the unreachable. Belt, suspenders.

## What a move also does

- **A look wins over face tracking** — `reachy_look` holds it for the move + 3 s.
- **Emotions are names, not angles** — a bad prompt cannot produce a bad pose.
- **Every tool returns an error string, never raises** — the model reads *"Cannot reach the Reachy Mini daemon…"*.

!!! tip "Beyond the hard limits"
    Small moves look natural — big swings read as malfunction. Nothing caps the head−body delta: stay under ~45°.

!!! note "No danger class"
    Unlike neon's mutex-gated walking and arm tools, every TINY tool is self-bounded. No `unsafe=True` — nothing to escape.
