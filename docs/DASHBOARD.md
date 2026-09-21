---
title: Dashboard — the cockpit (v4, twin picture-in-picture)
description: "Camera and MuJoCo twin as two layers of one viewport — swap, snap, size — plus the readout, the perception overlays and the keyboard, all straight from /api/state."
for: whoever drives the robot from a browser
proof: robot
verified: 2026-09-21
---

# Dashboard — the cockpit (v4: twin picture-in-picture)

!!! abstract "In 10 seconds"
    - `dashboard/server.py` (FastAPI `:8097`, passkey-gated) + a Vite/React SPA built on a laptop, shipped as `dist/`.
    - The camera fills the viewport; the **digital twin** (MuJoCo-WASM + three.js, mirroring the 10 Hz WS state) floats over it. A swap re-assigns boxes only — stream and sim never restart, the robot sees one camera client.
    - Every number on screen comes from `/api/state`; overlays render only when the field is present — no placeholders.
    - `space` = STOP, `D` = demo mode, `F` = face tracking, `T` = twin, `X` = swap.

```
┌ topbar ───────────────────────────────────────────────┐  ⚙ motors · 📶 dBm · 🌡 °C · 🧠/🎬 · 👁 track · 🔒
│ ● LIVE 10 fps   ⇄ 🧊 twin            ┌──────────────┐ │
│                                      │ 🧊 twin ⇄ S ✕ │ │  ← PiP card (drag · double-tap = swap)
│         live camera (MJPEG)          │   MuJoCo twin │ │
│                                      └──────────────┘ │
│                                      R −7° P 4° Y 11°  │  ← readout straight from /api/state
│  🧠 mind bubbles (last 3 agent rows)  ⟳−28° 📡−19/42 47Hz ⚙on
│                                                   [■] │  ← STOP (space)
└ cmdbar: Ask TINY…  🕹 🎭 🗣 🧠 ⚙ ─────────────────────┘
```

## The card (`components/PiP.tsx`)

| gesture / key | effect |
|---|---|
| drag the top strip | move; **snaps to the nearest corner** |
| double-tap, `X`, `⇄` chip | **swap** — twin full-bleed, camera in the card |
| `S` / `M` / `L` | 160×120 (phone default) · 320×240 (desktop default) · 480×360 (≥ 960 px) |
| `✕`, `T` | close — twin pauses; a `🧊 twin` chip brings it back |
| wheel / pinch · drag | zoom · orbit |

The card never covers STOP or the cmdbar; a bottom corner lifts the mind bubbles; landscape phones get a side-by-side split; ≤ 30 fps in the card; `prefers-reduced-motion` kills the idle spin. Prefs: `localStorage["reachy.pip.v1"]` `{corner, size, swapped, open, hinted}`.

## The readout

| cell | `/api/state` field |
|---|---|
| `R P Y` | `head.roll / pitch / yaw` (°) |
| `⟳` | `body_yaw` (°) |
| `📡 r/l` | `antennas[0] / antennas[1]` (°) |
| `Hz` | `daemon.loop_hz` |
| `⚙` | `control_mode` → on / off / g-comp |

## Perception overlays on the twin

| overlay | fields | meaning |
|---|---|---|
| gaze ring + face dot | `tracking.{enabled,detected,x,y,paused}` | daemon face tracker, `x,y ∈ [-1,1]`; amber = paused |
| DoA compass | `doa.angle` (rad), `doa.speech_detected` | ReSpeaker direction of arrival; 0 = front, counter-clockwise positive — flip the sign in `DoaArc` if it proves clockwise |
| `🫳 lifted` / `↗ tilted` | `imu.lifted`, `imu.tilted` | reserved — not published yet |

## Keyboard

`←→↑↓` look (`⇧` bigger) · `space` STOP · `H` home · `D` demo · `F` tracking · `T` twin · `X` swap · `L` look · `E` emotions · `/` ask · `esc`.

## Build · prove · deploy

```bash
cd dashboard/frontend && npm i && npm run build           # tsc -b + vite → dist/ (no node on the CM4)
BASE=$COCKPIT TOKEN=$REACHY_TOKEN node dashboard/frontend/scripts/pip-proof.mjs live
# ↑ Playwright: 25 checks at 390×844, 844×390, 1440×900 — geometry, snap, swap, one MJPEG stream, readout vs /api/state
rsync -az --delete dashboard/frontend/dist/ pollen@reachy-mini.local:tiny-the-reachy/dashboard/frontend/dist/   # no restart
ssh -N -L 18097:127.0.0.1:8097 pollen@reachy-mini.local   # local vite preview: proxy /api + /ws → :18097
```
