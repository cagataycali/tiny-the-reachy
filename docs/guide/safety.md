# safety envelope

<span class="read-badge">⏱ 30s</span>

Reachy Mini is a gentle desktop robot — no gait to fall, no arms to collide.
But the head is a Stewart platform with real limits, so both the SDK **and**
TINY's wrappers clamp every motion.

## the envelope

| joint | range |
|---|---|
| head pitch / roll | [-40, +40]° |
| head yaw | [-180, +180]° |
| body yaw | [-160, +160]° |
| head − body yaw delta | max 65° |

## where it's enforced

`_reachy_common.clamp()` enforces these limits inside `reachy_look` and
`reachy_body_turn` — *before* the values ever reach the daemon. The SDK clamps
again on its side. Belt and suspenders.

```python
# tools/_reachy_common.py (sketch)
def clamp(value, lo, hi):
    return max(lo, min(hi, value))
```

## practical rules

!!! tip "Good taste beyond the hard limits"
    - Small moves look most natural — big fast swings read as malfunction.
    - Keep the head−body yaw delta well under 65°; the wrapper caps it, but
      staying under ~45° keeps motion smooth.
    - Gentle collisions with the body are safe by design.

!!! note "No danger class"
    Unlike neon (whose walking/arm tools are FSM- and mutex-gated), TINY has no
    tool that can hurt the robot or a person. Every tool is self-bounded. There
    is no `unsafe=True` escape hatch because there's nothing to escape.
