---
title: Face tracking — daemon edition
description: "Since reachy-mini 1.10 the daemon detects faces (YuNet) and steers the head itself; this repo is a switch around it plus the two rules that make it coexist with moves, speech and the dashboard camera."
for: anyone wondering why the head follows you — or does not
proof: robot
verified: 2026-09-21
---

# Face tracking

!!! abstract "In 10 seconds"
    - **We do not detect faces.** Since daemon **1.10** YuNet runs inside it; this repo only switches and pauses it.
    - **ON at boot** (`REACHY_TRACK_AUTOSTART=1`); off: the 👁 pill / `F`, `head_tracking(False)`.
    - Cost: load 3.3 → 4.9, daemon CPU 135 %; dashboard fps held at 10.

## What 1.10 gave us

| SDK (`ReachyMini`) | daemon REST (`:8000`) | notes |
|---|---|---|
| `start_head_tracking(weight=1.0)` | `POST /api/media/tracking/enable {"weight": w}` | 1 follows; 0 paused |
| `stop_head_tracking()` | `POST /api/media/tracking/disable` | detector off |
| `get_tracked_face()` | `GET /api/media/tracking/face` | `{detected, x, y, roll, ts}` |

## The two rules

1. **The daemon owns the camera.** `rpicam-vid` locked it out (`imx708@1a is already in use`); the dashboard reads the daemon's IPC socket → 10 fps MJPEG.
2. **Moves and speech pause tracking.** At `weight ≥ 1` the daemon ignores head poses, so every move and speech takes a **named hold** (`speaking`, `emotion:cheerful1`, `look`) → weight 0, with a TTL.

## Where the pieces live

- `dashboard/tracking.py` — `Tracker`: enabled, holds, face poll, WS `{type:"tracking"}`.
- `dashboard/server.py` — `GET/POST /api/tracking`, `POST /api/tracking/hold {name,on,ttl}`.
- `dashboard/robot.py` — `express()/look()/say()` hold and release.
- `tools/head_tracking.py` — `head_tracking(enabled)`, `tracking_hold()`; `SpeakingHandoff`: first audio → hold, +0.8 s after → release.
- `Camera.tsx` `FaceMarker` — `x,y` on the frame; amber = paused.

```bash
cd dashboard && REACHY_NO_AUTOAPP=1 python -m pytest tests -q   # Tracker vs fake daemon (11) + gate (22)
python -m pytest tests/test_head_tracking.py -q                  # tools + SpeakingHandoff (7)
```
