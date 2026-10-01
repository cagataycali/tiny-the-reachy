---
title: Dashboard — the cockpit (v4, twin picture-in-picture)
description: "Camera and MuJoCo twin as two layers of one viewport — swap, snap, size — plus the readout, the perception overlays and the keyboard, all straight from /api/state."
for: whoever drives the robot from a browser
proof: robot
verified: 2026-09-21
---

# Dashboard — the cockpit

!!! abstract "In 10 seconds"
    - `dashboard/server.py` (FastAPI `:8097`, passkey-gated) + a Vite/React SPA in `dist/`.
    - The camera fills the viewport; the **digital twin** (MuJoCo-WASM + three.js) floats over it, mirroring WS state.

```
┌ STRANDS / reachy ─────────────────────────────────────┐  motors · dBm · C · thinker/demo · track · sound · lock
│ LIVE 10 fps   swap twin              ┌──────────────┐ │
│                                      │ twin  swap S x│ │  <- PiP card (drag · double-tap = swap)
│         live camera (MJPEG)          │   MuJoCo twin │ │
│                                      └──────────────┘ │
│                                      R -7 P 4 Y 11    │  <- readout straight from /api/state
│  mind cards (last 3 agent rows)       B -28 A -19/42 47 Hz on
│                                                [STOP] │  <- STOP (space), a solid ink square
└ cmdbar: Ask TINY   look L · emotions E · say · settings ┘
```

## The card (`components/PiP.tsx`)

| gesture / key | effect |
|---|---|
| drag the strip | move; **snaps to a corner** |
| double-tap, `X` | **swap**: twin full-bleed, camera in the card |
| `S` / `M` / `L` | 160×120 (phone) · 320×240 (desktop) · 480×360 |
| `x`, `T` | close; the `twin` chip brings it back |

The card never covers STOP; `prefers-reduced-motion` kills the spin.

## The readout

| cell | `/api/state` field |
|---|---|
| `R P Y` | `head.roll / pitch / yaw` (°) |
| `B` | `body_yaw` (°) |
| `A r/l` | `antennas[0] / antennas[1]` (°) |
| `Hz` | `daemon.loop_hz` |
| mode | `control_mode` → on / off / g-comp |

## Overlays on the twin

| overlay | fields | meaning |
|---|---|---|
| gaze ring, face dot | `tracking.{enabled,detected,x,y,paused}` | daemon tracker; amber = paused |
| DoA compass | `doa.angle` (rad), `doa.speech_detected` | ReSpeaker direction |

## Settings (runtime config)

Sections (voice, agent, telegram, personas) are generated from `tools/config.py` SCHEMA; values in `.memory/mem.db` override `.env` (`/api/config`; reset = env). Voice keys restart the live session; telegram and thinker follow next turn; API keys stay in `.env`.

## Design and keys

Strands tokens in `src/styles.css`; paper or dark via `html[data-scheme]`. `←→↑↓` look · `space` STOP · `H` home · `D` demo · `F` track · `T` twin · `X` swap · `E` emotions · `/` ask.

## Build · prove · deploy

```bash
cd dashboard/frontend && npm i && npm run build           # tsc -b + vite → dist/ (no node on the CM4)
BASE=$COCKPIT TOKEN=$REACHY_TOKEN node dashboard/frontend/scripts/pip-proof.mjs live
# ↑ Playwright: 25 checks at 390×844, 844×390, 1440×900 — geometry, snap, swap, one MJPEG stream, readout vs /api/state
rsync -az --delete dashboard/frontend/dist/ pollen@reachy-mini.local:tiny-the-reachy/dashboard/frontend/dist/   # no restart
ssh -N -L 18097:127.0.0.1:8097 pollen@reachy-mini.local   # local vite preview: proxy /api + /ws → :18097
```
