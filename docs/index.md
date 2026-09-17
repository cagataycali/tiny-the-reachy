---
title: Home
description: "TINY is a Reachy Mini Wireless that a Strands agent inhabits — voice, Telegram, a thinker, a cockpit at reachy.cagatay.my and a seat in the tiny.technology fleet. This is its manual, generated from the code that runs it."
hide:
  - navigation
  - toc
---

<section class="rh-hero" markdown>
<span class="rh-eyebrow"><b>Reachy Mini Wireless</b> · Raspberry Pi CM4 · Pollen daemon 1.10 · Strands · tiny.technology</span>

# I'm TINY. I live on the desk.

<p class="rh-lead">A Reachy Mini with a Strands agent inside. I hear (a 4-mic array that knows where a voice came from), see (a camera that follows your face), talk (OpenAI Realtime, voice <em>shimmer</em>) and move — a 6-DOF head, a turning body, two antenna ears and <strong>81 recorded emotions</strong>. Four personas share one brain; a cockpit streams my camera and a MuJoCo twin to your phone; and I can reach every other device in Çağatay's fleet.</p>

<p class="rh-cta">
<a class="md-button md-button--primary" href="start/quickstart/">Run it yourself</a>
<a class="md-button" href="https://reachy.cagatay.my">Open the cockpit ↗</a>
<a class="md-button" href="reference/tools/">The 26 tools</a>
</p>

<div class="rh-status" markdown>
<a class="rh-pill" href="https://reachy.cagatay.my/api/health" title="public JSON: daemon state, camera fps, fd pressure"><span class="rh-dot"></span> reachy.cagatay.my/api/health</a>
<a class="rh-pill" href="https://github.com/cagataycali/tiny-the-reachy/actions/workflows/docs.yml"><img alt="docs build" src="https://github.com/cagataycali/tiny-the-reachy/actions/workflows/docs.yml/badge.svg"></a>
<span class="rh-pill">reachy_mini <b>1.10.0</b></span>
<span class="rh-pill">voice <b>gpt-realtime-2 · shimmer</b></span>
<span class="rh-pill"><b>26</b> tools · <b>81</b> emotions · <b>37</b> API routes</span>
</div>
</section>

<figure class="rh-shot" markdown>
<img src="assets/cockpit-desktop.jpg" alt="The cockpit at reachy.cagatay.my on a 1440×900 desktop: live camera full-bleed, the MuJoCo twin as a picture-in-picture card with the pose readout, TINY's mind bubbles and the Ask bar" width="1440" height="900" loading="eager" decoding="async">
<figcaption>The cockpit, 2026-09-17: my camera full-bleed, the MuJoCo twin mirroring my real motors as a picture-in-picture, what I'm thinking in the bubbles. <a href="DASHBOARD/">How it works →</a></figcaption>
</figure>

## Three ways in

<div class="rh-paths" markdown>
<div class="rh-card" markdown>
### 🎙 Talk to TINY
Say something near the robot — the **voice persona** answers in shimmer and moves while it talks. Text it on **Telegram**, or type into the cockpit's **Ask** bar. Say *"silent"* and the speaker goes to 0 but the ears keep listening.

[Personas →](showcase/personas.md)
</div>
<div class="rh-card" markdown>
### 🛠 Run it yourself
A Reachy Mini (Lite on your laptop, or Wireless on its CM4), Python 3.12, AWS Bedrock for the text personas and an OpenAI key for the voice. `make venv && make run` gets you a REPL against the daemon; the robot itself runs eight user systemd units.

[Quickstart →](start/quickstart.md) · [Systemd →](start/systemd.md)
</div>
<div class="rh-card" markdown>
### 🧩 Hack on it
Every tool is a `@tool` function in `tools/` with a clamped envelope; the reference pages are generated from those docstrings at every build, so what you read is what the model reads. Add a tool, add a persona, add a device.

[Tools reference →](reference/tools/index.md) · [Extending →](guide/extending.md)
</div>
</div>

## How the pieces fit

```mermaid
flowchart LR
  subgraph body["🤖 the body — Reachy Mini Wireless, CM4"]
    HW["4 mics · camera · head/body/antenna motors · speaker · IMU"]
    D["reachy-mini daemon 1.10<br/>:8000 REST + WS · YuNet face tracker · DoA"]
    HW <--> D
  end
  subgraph personas["🧠 personas — user systemd units"]
    V["tiny-voice<br/>OpenAI Realtime · shimmer"]
    T["tiny-telegram"]
    K["tiny-thinker<br/>every 30 s"]
    S["shell · make run"]
  end
  BRAIN[("shared brain<br/>SQLite memory · agent log · dispatch")]
  DASH["reachy-dashboard :8097<br/>camera MJPEG · state WS · tracking holds · Ask"]
  TUN["cloudflared tunnel<br/>reachy.cagatay.my"]
  FLEET["tiny.technology<br/>fleet MCP · iOS app · other robots"]
  D <-->|SDK / REST| V & T & K & S
  V & T & K & S <--> BRAIN
  D <-->|"one keep-alive session,<br/>one state WebSocket"| DASH
  DASH --> TUN
  TUN <--> FLEET
  V & T & S <-.->|"use_device · tiny_recall"| FLEET
  DASH --- BRAIN
```

Everything is a client of Pollen's daemon — the personas never touch a motor directly, they call the
SDK; the dashboard is the one long-lived process every persona can reach, so it owns the face-tracking
controller and the camera stream. Details in [Architecture](guide/architecture.md).

## What's in the box

| | what | where |
|---|---|---|
| **Body** | head on a 6-DOF Stewart platform (pitch/roll ±40°, yaw ±180°), body ±160°, two antennas, 81 recorded moves | [Motion](reference/tools/reachy_motion.md) · [Expression](reference/tools/reachy_expression.md) |
| **Senses** | camera (daemon-owned, face tracked by YuNet inside the daemon), 4-mic array with direction of arrival, IMU | [Face tracking](FACE-TRACKING.md) · [State](reference/tools/reachy_state.md) |
| **Voice** | OpenAI Realtime `gpt-realtime-2`, voice `shimmer`; Piper TTS on the CM4 for the text personas; `reachy_volume` for "silent" | [Personas](showcase/personas.md) · [Audio](reference/tools/reachy_audio.md) |
| **Cockpit** | passkey-gated PWA: live camera, MuJoCo twin PiP, TINY's mind, Ask, demo mode, e-stop | [Dashboard](DASHBOARD.md) · [API](reference/api.md) |
| **Fleet** | `use_device` to Fomo the arm, Scout the rover, the Mac, the phone — and they can call TINY back (depth-capped) | [Fleet](MCP.md) |
| **Ops** | 8 user units + the daemon's `LimitNOFILE` drop-in and a 30 s watchdog; 73 env vars, all documented from code | [Systemd](start/systemd.md) · [Env](reference/env.md) |

<div class="rh-shots2" markdown>
<figure markdown>
<img src="assets/cockpit-phone.jpg" alt="The cockpit on a 390×844 phone: camera, twin PiP card in a corner, pills for motors, Wi-Fi and CM4 temperature" width="390" height="844" loading="lazy" decoding="async">
<figcaption>Phone, 390×844 — the same cockpit, twin in the corner.</figcaption>
</figure>
<figure markdown>
<img src="assets/cockpit-desktop-twin.jpg" alt="The cockpit with the twin swapped full-bleed and the camera in the picture-in-picture card" width="1440" height="900" loading="lazy" decoding="async">
<figcaption>Double-tap: twin full-bleed, camera in the card. One MJPEG client either way.</figcaption>
</figure>
<figure markdown>
<img src="assets/gate-desktop.jpg" alt="What an anonymous visitor sees at reachy.cagatay.my: the passkey gate — Continue, use a token, enrol another device" width="1280" height="800" loading="lazy" decoding="async">
<figcaption>Without a key you get the passkey gate — only <code>/api/health</code> is public.</figcaption>
</figure>
</div>

!!! note "Every page here is checked against the code"
    Tool pages, the env table and the API table are **generated at build** from `tools/*.py`, every `os.getenv`
    and `dashboard/server.py` (`scripts/tooldoc.py`, `envdoc.py`, `routedoc.py`); `tests/test_docs.py` fails when
    the two drift. Prose that could rot says *as of 2026-09-17* and names the file. If you find a lie,
    [open an issue](https://github.com/cagataycali/tiny-the-reachy/issues) — it's a bug like any other.
