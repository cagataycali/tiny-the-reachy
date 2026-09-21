# Dashboard — the cockpit (v4: twin picture-in-picture)

The showcase cockpit for TINY. Server: `dashboard/server.py` (FastAPI :8097 on the CM4, login-gated — see
`dashboard/README.md`). Frontend: Vite/React SPA in `dashboard/frontend`, built on a laptop, shipped as `dist/`.

## What you see

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

**Camera + twin at once.** The camera fills the viewport; the digital twin (MuJoCo-WASM + three.js, mirroring the real
motors from the 10 Hz WebSocket state) floats over it as a card. Both are *layers* of one viewport
(`components/PiP.tsx`): swapping only re-assigns their boxes, so the MJPEG stream and the physics sim never restart, the
robot always sees exactly one camera client, and the WS state rate does not change.

| gesture / key | effect |
|---|---|
| drag the card's top strip | move; it **snaps to the nearest corner** on release |
| double-tap / double-click the card, `X`, or the `⇄` chip | **swap** — twin full-bleed, camera in the card |
| `S`/`M`/`L` button on the card | size: **S** 160×120 (phone default) · **M** 320×240 (desktop default) · **L** 480×360 (≥ 960 px only — "twin large") |
| `✕` on the card, or `T` | **close** (twin pauses — no GPU work; sim keeps mirroring) → a `🧊 twin` chip brings it back; `T` again reopens |
| wheel / two-finger pinch inside the twin | zoom; one-finger drag orbits |
| ⚙ settings → *digital twin PiP* / *twin size* / *reset* | same controls without touching the card |

Layout rules: the card never covers STOP or the cmdbar (snap corners keep an 84 px bottom margin); a card in a bottom
corner **lifts the mind bubbles** above itself; landscape phones (height < 420 px) drop the floating card for a
**side-by-side split** (camera left, twin right, readout overlaid); the twin renders at **≤ 30 fps in the card**, the
idle orbit only spins when the twin is full-bleed, and `prefers-reduced-motion` disables the spin and the box
transitions.

Prefs persist in `localStorage["reachy.pip.v1"]`:
`{ corner: "tl"|"tr"|"bl"|"br", size: "S"|"M"|"L"|null (auto), swapped, open, hinted }`. Clear it to see the 3-second
first-visit hint again.

## The readout (details on the screen)

Under the card, every field comes from `/api/state` (the same payload the WS pushes):

| cell | field | unit |
|---|---|---|
| `R P Y` | `head.roll / pitch / yaw` | degrees |
| `⟳` | `body_yaw` | degrees |
| `📡 r/l` | `antennas[0] / antennas[1]` (right, left) | degrees |
| `Hz` | `daemon.loop_hz` (control loop) | Hz |
| `⚙` | `control_mode` → `on` / `off` / `g-comp` | — |

The strip exposes `data-roll/pitch/yaw/body` (1 decimal) for tests.

## Perception overlays on the twin

Rendered **only when the state carries the field**; absent or `null` → nothing (no placeholders). These are the field
names the perception lane keeps stable (`src/lib/api.ts` types `Tracking`, `Doa`, `Imu`):

| overlay | consumed fields | meaning |
|---|---|---|
| gaze ring + face dot | `tracking.enabled`, `tracking.detected`, `tracking.x`, `tracking.y`, `tracking.paused` | daemon face tracker (reachy-mini ≥ 1.10): `x,y ∈ [-1,1]` = face centre in the camera frame; dot = where the face sits relative to the head's gaze; amber while paused (`holds`) |
| DoA compass | `doa.angle` (rad), `doa.speech_detected` | ReSpeaker direction of arrival passed through the daemon's `/api/state/full`; 0 = front, drawn counter-clockwise-positive (robot's left). Convention to be confirmed empirically by the DoA lane — flip the sign in `DoaArc` if it turns out clockwise. |
| `🫳 lifted` / `↗ tilted` badge | `imu.lifted` or `imu.picked_up`, `imu.tilted` | IMU summary (not published yet — reserved) |

## Keyboard shortcuts

`←→↑↓` look (`⇧` = bigger step) · `space` STOP · `H` home · `D` demo mode (pause the thinker) · `F` face tracking ·
`T` twin PiP show/hide · `X` swap camera ⇄ twin · `L` look dock · `E` emotions · `/` ask · `esc` close. Ignored while
typing in a field.

## Build · prove · deploy

```bash
cd dashboard/frontend && npm i && npm run build           # tsc -b + vite → dist/ (no node on the CM4)
BASE=$COCKPIT TOKEN=$REACHY_TOKEN node dashboard/frontend/scripts/pip-proof.mjs live
# ↑ Playwright (from ~/.tiny/npm): 25 checks at 390×844, 844×390, 1440×900 — geometry, snap, swap, one MJPEG stream,
#   readout vs /api/state, persistence, 0 page errors; screenshots into $OUT (default /tmp/reachy-pip-proof)
rsync -az --delete dashboard/frontend/dist/ pollen@192.168.1.5:tiny-the-reachy/dashboard/frontend/dist/
# frontend-only change → no restart needed (index.html is served no-cache, assets are content-hashed)
```

Local preview against the real robot: `ssh -N -L 18097:127.0.0.1:8097 pollen@192.168.1.5` then a `vite preview` config
whose `preview.proxy` points `/api` + `/ws` at `http://127.0.0.1:18097` (sign in with the token in the gate).
