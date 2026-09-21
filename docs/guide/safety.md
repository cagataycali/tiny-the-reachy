---
title: Safety envelope
description: "What TINY clamps before a value reaches the daemon, what it deliberately leaves to the SDK, and where each limit lives in the code — read from tools/_reachy_common.py, not remembered."
for: anyone writing a motion tool or a prompt that moves the head
proof: code
verified: 2026-09-21
---

# Safety envelope

!!! abstract "In 10 seconds"
    - Head pitch/roll ±40°, head yaw ±180°, body yaw ±160° — `tools/_reachy_common.py:32-35`, applied by `clamp()` inside `reachy_look` and `reachy_body_turn` **before** the daemon is called.
    - Antennas (`~±90°`), head translation `x y z` (`~±20 mm`) and every recorded emotion are **not** clamped by TINY — the daemon and SDK bound them.
    - `MAX_YAW_DELTA = 65°` (head vs body) is declared and documented, but as of 2026-09-21 **no tool enforces it** — the daemon does.
    - There is no danger class and no `unsafe=True`: nothing here can hurt the robot or a person.

## The envelope

<div class="filterable" data-id="limit" data-placeholder="pitch, body, antenna…" markdown>

| value | limit | enforced by | where |
|---|---|---|---|
| head pitch | ±40° | TINY `clamp()` → then SDK | `_reachy_common.py:32` · `reachy_motion.py:62` |
| head roll | ±40° | TINY `clamp()` → then SDK | `_reachy_common.py:33` · `reachy_motion.py:63` |
| head yaw | ±180° | TINY `clamp()` → then SDK | `_reachy_common.py:34` · `reachy_motion.py:64` |
| body yaw | ±160° | TINY `clamp()` → then SDK | `_reachy_common.py:35` · `reachy_motion.py:66,118` |
| head − body yaw delta | 65° | daemon only — declared, not applied | `_reachy_common.py:36` (`MAX_YAW_DELTA`, unused) |
| antennas | ~±90° | daemon / SDK | `reachy_antennas` docstring; radians passed straight through |
| head translation x y z | ~±20 mm | daemon / SDK (Stewart platform reach) | `create_head_pose(mm=True)` — no TINY clamp |
| move duration | ≥ 0.1 s | TINY `max(0.1, duration)` | `reachy_motion.py` every `goto_target` |
| recorded emotions | the daemon's own library | daemon | `reachy_express` only sends a *name* |

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

The SDK clamps again on its side, and the daemon's kinematics reject what the platform cannot reach. Belt, suspenders, and a floor.

## What a move also does

- **An explicit look wins over face tracking.** `reachy_look` calls `_hold_tracking("look", …)` for the move's duration + 3 s, so the daemon's face tracker (≥ 1.10) does not fight the pose; tracking resumes by itself — [head tracking](../reference/tools/head_tracking.md).
- **Emotions are names, not angles.** `reachy_express("cheerful1")` asks the daemon to play its own recorded move; TINY never synthesises the trajectory, so a bad prompt cannot produce a bad pose — [expression](../showcase/expression.md).
- **Every tool returns an error string, never raises.** With the daemon down the model reads *"Cannot reach the Reachy Mini daemon…"* and says so; nothing else in the process breaks.

## Practical rules

!!! tip "Good taste beyond the hard limits"
    - Small moves look most natural — big fast swings read as malfunction.
    - Keep the head−body yaw delta well under 65°; nothing in TINY caps it today, so stay under ~45° in prompts and examples.
    - Gentle contact with its own body is safe by design; there is nothing to pinch.

!!! note "No danger class"
    Unlike neon (whose walking and arm tools are FSM- and mutex-gated), TINY has no tool that can hurt the robot or a person. Every tool is
    self-bounded. There is no `unsafe=True` escape hatch because there is nothing to escape.
