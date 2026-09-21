---
title: Face tracking — daemon edition
description: "Since reachy-mini 1.10 the daemon detects faces (YuNet) and steers the head itself; this repo is a switch around it plus the two rules that make it coexist with moves, speech and the dashboard camera."
for: anyone wondering why the head follows you — or does not
proof: robot
verified: 2026-09-21
---

# Face tracking — daemon edition

!!! abstract "In 10 seconds"
    - **We do not detect faces.** Since reachy-mini **1.10** the daemon runs YuNet and eases the head toward the face (`alpha 0.15`); this repo only switches and pauses it.
    - Default **ON at boot** (`REACHY_TRACK_AUTOSTART=1`, `server.py:537`); off: `0`, the 👁 pill / `F`, `head_tracking(False)`.
    - Rule 1: the daemon owns the camera → the dashboard reads its IPC socket (`REACHY_DASH_CAMERA=ipc`), never `rpicam-vid`.
    - Rule 2: at `weight ≥ 1` the daemon ignores `set_target_head_pose` → every move and speech turn takes a **named hold** (weight 0, TTL).
    - Cost on the CM4: load 3.3 → 4.9, daemon CPU 135 %; dashboard fps held at 10.

## What 1.10 gave us

| SDK (`ReachyMini`) | daemon REST (`:8000`) | notes |
|---|---|---|
| `start_head_tracking(weight=1.0)` | `POST /api/media/tracking/enable {"weight": w}` | 1 = tracking owns the head; 0 = paused. `enabled:false` without a camera |
| `stop_head_tracking()` | `POST /api/media/tracking/disable` | detector stopped |
| `get_tracked_face()` | `GET /api/media/tracking/face` | `{detected, x, y, roll, ts}` · `x, y ∈ [-1, 1]` |

## The two rules

1. **The daemon owns the camera.** `rpicam-vid` locked it out (`imx708@1a is already in use`). `Camera._run_ipc`: `unixfdsrc ! queue ! v4l2convert ! I420 640x360 ! jpegenc ! appsink` → 10 fps MJPEG, ~25 KB/frame; re-acquires within ~1 s after any media release.
2. **Moves and speech pause tracking** (Pollen's `set_speaking`). Named holds — `speaking`, `emotion:cheerful1`, `look` — any live hold → weight 0. `speaking` only bites once a face is locked, so speech cannot block acquisition.

## Where the pieces live

- `dashboard/tracking.py` — `Tracker`: enabled, holds, face poll, WS `{type:"tracking"}`.
- `dashboard/server.py` — `GET/POST /api/tracking`, `POST /api/tracking/hold {name,on,ttl}`; loopback writes need no key.
- `dashboard/robot.py` — `express()/look()/say()` hold and release.
- `tools/head_tracking.py` — `head_tracking(enabled)`, `head_tracking_status()`, `tracking_hold()`; `SpeakingHandoff` (voice): first audio → hold, response complete +0.8 s or interruption → release.
- `Camera.tsx` `FaceMarker` — daemon `x,y` on the frame; amber = paused.

```bash
cd dashboard && REACHY_NO_AUTOAPP=1 python -m pytest tests -q   # Tracker vs fake daemon (11) + gate (22)
python -m pytest tests/test_head_tracking.py -q                  # tools + SpeakingHandoff (7)
```
