# Face tracking — daemon edition

TINY follows the closest face with its head. **We do not detect faces ourselves**: since
reachy-mini **1.10.0** the daemon runs a YuNet detector on its own camera pipeline and blends the
head toward the face in its control loop. Everything in this repo is a thin switch around it,
modelled on Pollen's `reachy_mini_conversation_app` (`tools/head_tracking.py` + `moves.py`).

Default **OFF**. Turn it on from the dashboard (👁 pill, key `F`), from any persona
("follow me" → `head_tracking(True)`), or at boot with `REACHY_FACE_TRACKING=1`.

## What 1.10 gave us

| SDK (`ReachyMini`) | daemon REST (`:8000`) | notes |
|---|---|---|
| `start_head_tracking(weight=1.0)` | `POST /api/media/tracking/enable {"weight": w}` | `weight` 1 = tracking owns the head; 0 = detector paused, head free, aim cleared. Returns `enabled:false` when the daemon has **no camera** |
| `stop_head_tracking()` | `POST /api/media/tracking/disable` | detector thread stopped |
| `get_tracked_face(wait, timeout)` → `FaceTarget` | `GET /api/media/tracking/face` | `{detected, x, y, roll, ts}`; `x, y ∈ [-1, 1]` face centre in the camera frame (+x right, +y down) |

Behaviour inside the daemon (`daemon/backend/abstract.py`): aim eased toward the face
(`alpha 0.15`), a 2 s detection gap holds the last aim, a longer loss recentres to neutral.
**While `weight ≥ 1` the daemon ignores `set_target_head_pose`** — emotions, `goto`, `look_at`
are overridden. That is why moves must *pause* tracking (see holds).

## The two hard constraints (and how we meet them)

1. **The daemon must own the camera.** Its tracker reads frames from the daemon's own
   `GstMediaServer` IPC branch (`/tmp/reachymini_camera_socket`, 10 fps). Before this change the
   dashboard streamed the sensor with `rpicam-vid`, which locked the daemon out
   (`Camera '/base/soc/…imx708@1a' is already in use` in its log) → tracking impossible.
   The dashboard camera now has an **`ipc` backend** (`dashboard/robot.py: Camera._run_ipc`):
   `unixfdsrc ! queue ! v4l2convert ! I420 640x360 ! jpegenc ! appsink` → 10 fps MJPEG, ~25 KB/frame.
   Anything that releases media (SDK clients with `media_backend="no_media"`, `voice_listener`'s
   `POST /api/media/release`) kills the socket → the backend re-acquires it
   (`POST /api/media/acquire`) and resumes within ~1 s (proven with a live voice restart).
   `REACHY_DASH_CAMERA=rpicam|cv2` forces the old backends (tracking then cannot work).
2. **Moves and speech must pause tracking** (Pollen `MovementManager.set_speaking`). `dashboard/tracking.py`
   keeps *named holds*: `hold("speaking")`, `hold("emotion:cheerful1")`, `hold("look")`… Any live hold →
   weight `0.0`; none → `1.0`. Holds carry a TTL so a crashed persona can never freeze the head. The
   `speaking` hold only bites once a face is locked (otherwise speech would block acquisition — Pollen's rule).

## Where the pieces live

- `dashboard/tracking.py` — `Tracker` (enabled, holds, ≤5 Hz face poll, WS `{type:"tracking"}`, `stop()` on shutdown).
- `dashboard/server.py` — `GET/POST /api/tracking`, `POST /api/tracking/hold {name,on,ttl}`; gated like every
  `/api/*` route. **Loopback allowance**: from `127.0.0.1` with a loopback `Host` and no Cloudflare headers these two
  POSTs need no key (`auth.loopback_write`), so the personas on the robot can toggle without a token.
  `REACHY_LOOPBACK_READS=0` disables it. `state.tracking` mirrors the status.
- `dashboard/robot.py` — `express()/look()/say()` hold and release around the move; `Camera` `ipc` backend.
- `tools/head_tracking.py` — Strands tools `head_tracking(enabled)`, `head_tracking_status()` (thinker, telegram,
  dashboard Ask, voice); `tracking_hold()`; `stop_head_tracking()` (shutdown hook, Pollen `moves.py` ~661);
  `SpeakingHandoff` — a `BidiOutput` for the voice persona: first `bidi_audio_stream` → hold, `bidi_response_complete`
  (+0.8 s tail) / `bidi_interruption` → release.
- `tools/reachy_expression.py`, `tools/reachy_motion.py` — SDK-side moves hold/release the same way.
- Frontend: `Camera.tsx` `FaceMarker` (daemon `x,y` → % of the frame; amber = paused), 👁 pill in the top bar.

## Cost (measured on the CM4, 2026-09-17, nobody in frame)

| | load1 | daemon CPU | dashboard fps |
|---|---|---|---|
| tracking OFF | 2.8–3.5 | 55–80 % | 10.0 |
| tracking ON (60 s) | 3.3 → **4.9** | 135 % (detector thread 54 % at nice 19) | 10.0 (never dropped) |

The fps floor (8) held; the load budget (3.5) did not → **default stays OFF**, enable on demand.
`REACHY_FACE_TRACKING=1` in `~/.reachy-dashboard.env` turns it on at boot if you accept the load.

## Turning it off / removing it

- Instantly: 👁 pill, key `F`, `head_tracking(False)`, or `POST /api/media/tracking/disable` on the daemon.
- Personas stop tracking on shutdown; the dashboard does on its shutdown hook.
- To go back to the pre-1.10 camera path: `REACHY_DASH_CAMERA=rpicam` in `~/.reachy-dashboard.env` (tracking will then
  report *unavailable: daemon has no camera*).

## Tests

```
cd dashboard && REACHY_NO_AUTOAPP=1 python -m pytest tests -q      # Tracker vs fake daemon (11) + gate (22)
python -m pytest tests/test_head_tracking.py -q                     # tools + SpeakingHandoff vs fake dashboard (7)
```
