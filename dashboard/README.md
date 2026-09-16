# Reachy Mini showcase dashboard — reachy.cagatay.my

FastAPI (:8097, `dashboard/server.py`) + prebuilt Vite/React SPA (`dashboard/frontend/dist`), running **on the robot**
under `/venvs/apps_venv` as the user unit `reachy-dashboard.service`, exposed by the existing `reachy-tunnel.service`
(cloudflared → http://localhost:8097). Public visitors watch (camera, pose avatar, emotions, shared agent log);
the owner drives after a passkey or bearer sign-in.

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
