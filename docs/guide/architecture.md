# architecture

<span class="read-badge">⏱ 90s</span>

How `tiny` fits together — and how it differs from its siblings.

## physical layout

```
Reachy Mini
├─ your laptop (Lite)  OR  onboard CM4 (Wireless)   ← runs tiny + the daemon
│    tiny agents → .venv/bin/python agent.py   (or docker compose)
│      Strands loop · TINY_ALL_TOOLS (14) · voice/telegram/thinker
│    reachy-mini daemon (FastAPI) on :8000     ← owns the hardware
▼
└─ Reachy Mini hardware
     6-DOF head (Stewart platform) · rotating body · 2 antennas
     camera · microphone · speaker · IMU
```

**Key difference from neon:** Reachy has **no DDS, no CycloneDDS, no
librealsense**. Control is plain HTTP/WS to the daemon on `:8000`. The Docker
image is *light* — no motor-bus build, no realsense compile.

## the agent loop

```mermaid
flowchart LR
  M(["📨 message"]) --> I["inject live state<br/>(head pose · antennas · imu)"]
  I --> P["🎯 model plans tool calls"]
  P --> T["⚡ execute (expression + speech together)"]
  T --> R["💬 synthesize reply"]
  R --> U(["📤 user"])
  classDef a stroke:#7a6aa8,stroke-width:1.5px
  class I,P,T,R a
```

Every turn injects the shared cross-persona log + live pose into the prompt, so
the model wakes up already knowing what the other personas did and where the
head is.

## the tool layers

```mermaid
flowchart LR
  A(["🤖 agent"]) --> R["🟣 robot tools<br/>reachy_*"]
  A --> B["🧠 cross-persona brain<br/>memory · agent_log · voice_bridge"]
  A --> M["🔧 meta<br/>dispatch · manage_*"]
  R --> D["⚙️ reachy daemon :8000"]
  classDef a stroke:#7a6aa8,stroke-width:1.5px
  class R,B,M a
```

- **robot tools** — 14 `reachy_*` wrappers, all through a cached `get_mini()` client
- **cross-persona brain** — copied verbatim from neon (see [the brain](brain.md))
- **meta** — `dispatch` (spawn sub-agents), `manage_messages`, `manage_tools`

## single source of truth

All persona / tool / prompt wiring lives in `tiny.py`:

```python
build_agent(persona)     # generic factory
build_shell_agent()      # REPL
build_voice_agent()      # bidi voice
# thinker + telegram personas built from the same list
```

One tool list, four personas. Change a tool once, every face gets it.
