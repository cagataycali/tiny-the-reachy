# Reachy Mini showcase dashboard — reachy.cagatay.my

FastAPI (:8097, `dashboard/server.py`) + prebuilt Vite/React SPA (`dashboard/frontend/dist`), running **on the robot**
under `/venvs/apps_venv` as the user unit `reachy-dashboard.service`, exposed by the existing `reachy-tunnel.service`
(cloudflared → http://localhost:8097). **Login-gated like scout.cagatay.my (v3):** nothing under `/api/*` or `/ws`
answers without a key — only `GET /api/health`, the `/api/auth/*` routes and the static SPA shell (so the sign-in card
can render) are public. Keys, in `auth.who()` order: `Authorization: Bearer <REACHY_TOKEN>` (or `?token=` — the MJPEG
`<img>` and the WebSocket cannot set headers), a passkey session cookie, loopback-dev.
One documented allowance, `auth.loopback_read()`: GET requests from the robot itself (client 127.0.0.1, loopback Host,
no `cf-connecting-ip`) pass without a key so the personas' `tools/reachy_camera.py` keeps reading `/api/snapshot.jpg`;
tunnel traffic also arrives from 127.0.0.1 but carries the public Host + Cloudflare headers and is refused.
`REACHY_LOOPBACK_READS=0` turns it off. Tests: `cd dashboard && REACHY_NO_AUTOAPP=1 python -m pytest tests -q`.

```
dashboard/deploy/sync.sh          # rsync dashboard/ + dist/ to pollen@192.168.1.5 and restart the unit
cd dashboard/frontend && npm i && npm run build   # rebuild the SPA on a laptop (no node on the CM4)
```

Secrets: `/home/pollen/.reachy-dashboard.env` (REACHY_TOKEN, REACHY_REG_TOKEN, REACHY_RP_ID, REACHY_ORIGIN) — never in git.
Camera: the Wireless camera is a CSI sensor behind libcamera; `cv2.VideoCapture(0)` yields no frames, so the server pipes
`rpicam-vid --codec mjpeg 640x360@12` (`REACHY_DASH_CAMERA=cv2` for UVC webcams). The daemon must have released media
(`POST :8000/api/media/release`) — the voice persona normally does this.
Routes: see the docstring at the top of `server.py`. Every control write is logged to the personas' shared `agent_log`
as persona `dashboard`.
