---
title: Tool playbook — gestures that fall out of the tools
description: "The recipes, not the signatures: how a nod, a curious tilt, a droop, a glance and a look-at-me come out of 28 tools — and the one rule that makes them read as alive."
for: anyone writing a prompt, a persona note or a new gesture
proof: code
verified: 2026-09-21
---

# Tool playbook — gestures that fall out of the tools

!!! abstract "In 10 seconds"
    - 28 tools, [signatures generated from the code](../reference/tools/index.md): 19 `reachy_*` on the body, 8 shared brain tools, `use_device` for the fleet.
    - Degrees for angles, millimetres for translation, every value [clamped](../guide/safety.md) before the daemon sees it.
    - **The rule** (`prompts/base.md`): a gesture fires **in the same batch as the words**, never before or after.
    - Small, frequent motion reads as alive; big fast swings read as malfunction.

## Head, antennas, body

```python
reachy_look(pitch=15); reachy_look(pitch=-10)        # nod
reachy_look(roll=15)                                  # curious tilt
reachy_look(x=20, pitch=10)                           # lean in
reachy_antennas(45, 45)   # alert · (60, 60) excited · (-40, -40) droop
reachy_body_turn(30)                                  # face whoever is talking — keep head−body under ~45°
reachy_home() · reachy_wake() · reachy_wake(sleep=True)
```

`reachy_look` also takes `antennas=[right, left]` and `body_yaw`, so one call can be a whole posture.

## Feelings by name

```python
reachy_express("happy")      # → cheerful1 — plain names resolve to the library's 81 takes
reachy_express("no")         # → no1, the head shake
reachy_express("curious")    # → curious1
reachy_list_emotions()       # the real names, from RecordedMoves.list_moves()
```

The library downloads on first use — the first call takes a moment. Why it reads as alive: [Expression](../showcase/expression.md).

## Eyes

```python
take_photo(question="who is in front of me?")        # a frame INTO the conversation — TINY reasons about it, then answers aloud
reachy_camera(save_path="/tmp/tiny_view.jpg")        # a JPEG on disk (the thinker's every cycle)
reachy_look_at(u, v)                                 # point the head at a pixel
```

"look at me", "what's this?", "read this to me" are all `take_photo` with a different question.

## Voice

```python
reachy_say("hi there!")      # Piper → speaker, head wobbles while it talks
reachy_express("happy")      # …in the same batch: spoken AND expressed at once
reachy_volume(0)             # "silent" — keep listening
```

Text personas that want to be heard call `reachy_say`; `voice_say` queues for a voice session that does not drain the queue yet ([the brain](../guide/brain.md)).

## The brain

`memory` · `agent_log` · `voice_say` · `telegram` · `dispatch` · `prompts` · `manage_messages` · `manage_tools` — verbatim from neon, [documented once](../guide/brain.md).
