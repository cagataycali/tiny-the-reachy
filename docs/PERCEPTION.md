---
title: Perception — face tracking · turn to sound · daemon pressure
description: "Three layers steer the head from one daemon WebSocket: the daemon's own face tracker, a six-rule turn-to-sound, and a pressure gauge born from the EMFILE incident. What wins when they disagree."
for: whoever tunes how TINY notices you
proof: robot
verified: 2026-09-17
---

# Perception

!!! abstract "In 10 seconds"
    - Three layers, one daemon WebSocket.
    - A look / say holds the tracker; a face lock blocks DoA — it acts only when nobody is in view.
    - New code: **read `robot.stream`, never poll the daemon.**

| layer | source | module | switch |
|---|---|---|---|
| **face tracking** | daemon YuNet | `dashboard/tracking.py` | 👁 `F` · `head_tracking()` |
| **turn to sound** | ReSpeaker DoA | `dashboard/doa.py` | 🔊 `K` · `turn_to_sound()` |
| **IMU** | daemon `imu` | `state.imu` | twin badge |

## Face tracking

The detector runs inside the daemon — the dashboard only toggles weight: `1` follow, `0` paused. Details: [FACE-TRACKING.md](FACE-TRACKING.md).

## Turn to sound (DoA)

**0 = left, π/2 = front/back, π = right** — a linear array cannot tell front from back. A turn fires when **all** hold:

1. speech on ≥ 6 frames agreeing within ±12°;
2. not a **rail** (within 3° of 0 or π — its own speaker);
3. TINY **not speaking** (+1.5 s);
4. no face lock, hold or move in flight; ≥ 3 s since the last;
5. |delta| ≥ 10°;
6. **windup guard**: a same-direction turn within 10 s whose bearing did not shrink 40 % is refused — the sound moved with the head.

Then one `goto`: head to ±45°, body carries the rest; `GET /api/doa` shows `why`.

## Fields the cockpit consumes

```jsonc
"tracking": {"enabled", "paused", "holds", "detected", "x", "y", "roll", "weight", "available", "error", "face_age_s", "reasserts"},
"doa":      {"angle": 1.57, "speech_detected": true},        // rad, Pollen convention → twin DoaArc
"doa_turn": {"enabled", "armed", "speech", "angle_deg", "delta_deg", "turns", "windups", "why", "sign", "calib": {...}},
"imu":      {"lifted"|"picked_up", "tilted"},
"pressure": {"pid", "fds", "fd_limit", "close_wait", "established", "warn"},
"stream":   {"connected", "hz", "frames", "reconnects", "age_s", "error"},
"state_age_s": 0.04
```

## Daemon pressure

After the EMFILE incident: one WebSocket for every consumer — **≈160 requests/min, 0 CLOSE-WAIT**. Timeline: [Operations](guide/operations.md).
