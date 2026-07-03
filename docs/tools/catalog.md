# tool catalog

<span class="read-badge">⏱ 90s · 14 robot tools</span>

Every `@tool` in `tools/`, grouped by what it touches. TINY has **no arms, no
legs, no FSM** — control is dead simple, so there's no danger class. Everything
is clamped to the head/body/antenna envelope by the SDK *and* our wrappers.

<div class="motion-legend" markdown>
<span><span class="dot" style="background:#57c98a"></span>read-only — state / sensing</span>
<span><span class="dot" style="background:#b39ddb"></span>motion — clamped, self-bounded</span>
<span><span class="dot" style="background:#2e8b8b"></span>io — audio / camera</span>
</div>

## 🟣 motion · 5

| tool | what |
|---|---|
| `reachy_look` | move the 6-DOF head — `x,y,z` mm + `roll,pitch,yaw` deg (the primary gesture) |
| `reachy_antennas` | move the two "ears" — `right,left` in degrees (emotion in a flick) |
| `reachy_body_turn` | rotate the body around vertical — `yaw` deg, clamped [-160, 160] |
| `reachy_home` | return to neutral/init pose (head centered, antennas at rest) |
| `reachy_wake` | wake up (init + wake emote + sound) or `sleep=True` to sleep |

[Full motion reference →](motion.md)

## 🟣 expression · 2

| tool | what |
|---|---|
| `reachy_express` | play a named emotion/dance from the recorded-move library |
| `reachy_list_emotions` | list every emotion name available in the library |

Backed by `pollen-robotics/reachy-mini-emotions-library` — downloaded live on
first use. [Full expression reference →](expression.md)

## 🟢 state · 2

| tool | what |
|---|---|
| `reachy_get_state` | live head pose, joint positions, IMU (if present) |
| `reachy_motors` | set torque mode — `enabled` / `disabled` / gravity-comp |

## 🟢 sensing · 2

| tool | what |
|---|---|
| `reachy_camera` | grab a frame from the head camera, save to disk |
| `reachy_look_at` | look at pixel `(u,v)` in the camera frame (visual servoing) |
| `take_photo` | bidi vision — inject an image into the conversation with a question |

[Full sensing reference →](sensing.md)

## 🔵 audio · 3

| tool | what |
|---|---|
| `reachy_say` | **speak** text via TTS, with synced head-wobble (the way TINY talks) |
| `reachy_play_sound` | play a local/daemon sound file through the speaker |
| `reachy_volume` | get or set speaker volume (0–100) |

## 🧠 cross-persona brain

Copied **verbatim** from neon — the shared nervous system every persona uses.
See [the brain](../guide/brain.md).

| tool | what |
|---|---|
| `memory` | SQLite kv/log + filesystem notes |
| `agent_log` | unified cross-persona reasoning log |
| `voice_bridge` / `voice_say` | briefing queue → speak on the voice persona |
| `telegram` | Telegram Bot API + per-chat history |
| `dispatch` | spawn devduck sub-agents (cron / run_at / background) |
| `prompts` | per-persona prompt overrides (SQLite) |
| `manage_messages` | trim / compact own history |
| `manage_tools` | load / create tools at runtime |
