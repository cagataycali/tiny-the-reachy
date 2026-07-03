---
hide:
  - navigation
  - toc
---

<div class="hero" markdown>

<img src="assets/tiny.svg" alt="tiny" class="logo"/>

<p class="tagline">a strands agent on the reachy mini · on the desk</p>

<div class="buttons" markdown>
[:material-rocket-launch: 3-minute tour](start/quickstart.md){ .md-button .md-button--primary }
[:material-github: GitHub](https://github.com/cagataycali/tiny-the-reachy){ .md-button }
</div>

<div class="stat-row" markdown>
<span class="stat-pill"><span class="dot"></span> <strong>&nbsp;live on Reachy</strong></span>
<span class="stat-pill"><strong>14</strong> robot tools</span>
<span class="stat-pill"><strong>4</strong> personas</span>
<span class="stat-pill"><strong>6-DOF</strong> head</span>
<span class="stat-pill"><strong>2</strong> antennas</span>
</div>

</div>

<div class="type-demo" markdown>
<span class="line"><span class="prompt">tiny&nbsp;&gt;</span> say hi and show me you're happy</span>
<span class="line"><span class="out">  → reachy_express('happy')</span>     <span class="ok">rc=0 · antennas wiggle</span></span>
<span class="line"><span class="out">  → reachy_say('hey there!')</span>    <span class="ok">rc=0 · head wobble</span></span>
<span class="line"><span class="prompt">tiny&nbsp;&gt;</span> Hey! 👋 <span class="cur"></span></span>
</div>

---

<div class="tour" markdown>

## the whole thing in 3 minutes

<div class="tour-step" markdown>
<span class="tour-num">1</span>
**What it is.** A [Strands](https://github.com/strands-agents) agent that drives a
**Reachy Mini** (Pollen Robotics). It's a pure client of the Reachy **daemon**
(`:8000`), turning every SDK call into a typed, clamped tool. Runs on your
laptop (Lite) or the onboard CM4 (Wireless).
</div>

<div class="tour-step" markdown>
<span class="tour-num">2</span>
**How you talk to it.** One agent, four faces — REPL, voice, Telegram, thinker.
Say `look at me`, `wiggle your antennas`, `what do you see?`, `spin around`.
It plans, fires expressions *while* speaking, and replies.
</div>

<div class="tour-step" markdown>
<span class="tour-num">3</span>
**Why it's expressive.** No arms, no legs — personality lives in a 6-DOF head,
a rotating body, two antenna "ears", and a recorded-emotion library. Every
answer moves. Small moves look best; the SDK clamps the envelope.
</div>

[Start the tour →](start/quickstart.md){ .md-button .md-button--primary }

</div>

```mermaid
flowchart LR
  U(["🗣️ you"]) -->|"voice · telegram · REPL"| A

  subgraph DESK["🤖 Reachy Mini · desktop"]
    direction TB
    A["🧠 tiny<br/>strands · 14 tools"]
    D["⚙️ reachy daemon<br/>:8000 HTTP/WS"]
    M["🦾 6-DOF head · body<br/>antennas · speaker"]
    S[("👁️ camera · imu<br/>microphone")]
    A -->|"SDK client"| D --> M
    A -.->|"read-only"| S
  end

  classDef brain stroke:#7a6aa8,stroke-width:1.5px
  classDef io stroke:#2e8b8b,stroke-width:1.5px
  class A brain
  class S,D io
```

---

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg } **Quickstart**

    ---

    Clone, set your keys, `make run`. First wobble in 60 seconds.

    [→ quickstart](start/quickstart.md)

-   :material-hand-wave:{ .lg } **Expression**

    ---

    How tiny turns emotion into head + antenna + body motion.

    [→ expression](showcase/expression.md)

-   :material-toolbox:{ .lg } **Tool catalog**

    ---

    All 14 robot tools + the shared cross-persona brain.

    [→ catalog](tools/catalog.md)

-   :material-family-tree:{ .lg } **The family**

    ---

    neon (G1) · scout (rover) · tiny (Reachy). One brain, three bodies.

    [→ family](reference/family.md)

</div>
