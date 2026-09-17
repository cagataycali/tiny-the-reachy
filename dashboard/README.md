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

## Frontend v3 (2026-09-17) — mobile-first cockpit, the agent as an overlay

`Gate` → `Cockpit`. Nothing but the passkey card renders until `/api/auth/status` says `authenticated` (TOFU first
enrol → passkey login → "use a token" fallback → "enrol another device" with `REACHY_REG_TOKEN`). The cockpit unmounts on
🔒 lock, on any 401 and on a gated WebSocket hello, so a lost session goes straight back to the card.

Layout (`src/App.tsx`, `src/styles.css`): glass **topbar** (state pills: motors · Wi-Fi dBm · CM4 °C · demo/thinker
toggle · 🔒) · full-bleed **viewport** = live camera **with the MuJoCo twin as a picture-in-picture card** (v4, see `docs/DASHBOARD.md`: drag/snap, double-tap or `X` to swap, `T` to hide, readout of head R/P/Y · body · antennas · Hz · mode under it) · **agent overlay** = the last mind rows as
glass bubbles over the picture, dimming with age, the live Ask stream with a caret (tap → the full timeline sheet) ·
**STOP** always visible in the viewport corner (`space`) · bottom **cmdbar** = Ask box + 🕹 look pad / 🎭 emotions & reel
/ 🗣 say / 🧠 mind / ⚙ settings as slide-up sheets. ≥960 px: viewport left, mind timeline (or the open dock) right.
Keys: `←→↑↓` look · `space` STOP · `H` home · `D` demo · `F` face-track · `T` twin PiP · `X` swap · `L` look · `E` emotions · `/` ask · `esc` close.

PWA: `public/manifest.webmanifest` (standalone, icons, shortcuts `?action=ask|reel`) + `public/sw.js` (app shell only:
`/assets/*` cache-first, `/` network-first with offline fallback; never `/api`, `/ws`, `/model`, `/mujoco`). The server
sends `Cache-Control: no-cache` for `index.html`, `sw.js` and the manifest so Cloudflare never pins an old shell.
`<img /api/stream>` carries `?token=` in bearer mode (`api.streamUrl()`); in passkey mode the session cookie rides along.
Proof scripts live in `~/.tiny/reachy-v3-20260917/*.mjs` (Playwright, 390×844 + 1280×800); the v4 PiP proof is in-repo:
`BASE=… TOKEN=… node scripts/pip-proof.mjs` (25 checks at 390×844, 844×390, 1440×900).
