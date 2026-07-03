# expression showcase

<span class="read-badge">⏱ 60s</span>

TINY is not a chatbot with a body bolted on — it's *embodied*. Every answer
moves. This is the playbook from `prompts/base.md`, the thing that makes TINY
feel alive on a desk.

## the golden rule

> Gestures happen **simultaneously** with speech — never before, never after.

The model batches an expression call and a `reachy_say` call in the same turn,
so the antenna wiggle lands on the word "hi", not two seconds later.

## the playbook

| you say / TINY feels | TINY does |
|---|---|
| "hi" / "hello" | `reachy_express('happy')` or `reachy_antennas(45, 45)` |
| agreement / "yes" | `reachy_look(pitch=15)` then `reachy_look(pitch=-10)` — a nod |
| disagreement / "no" | `reachy_express('no')` — head shake |
| curious / new person | `reachy_express('curious')` or `reachy_look(roll=15)` |
| excitement | `reachy_antennas(60, 60)` + `reachy_body_turn(20)` |
| sadness | `reachy_antennas(-40, -40)` + `reachy_look(pitch=-20)` |
| surprise | `reachy_express('surprised')` |
| turn toward speaker | `reachy_body_turn(yaw=±30)` |

Discover the whole recorded library with `reachy_list_emotions`.

## a full turn

<div class="terminal" markdown>
<span class="p">&gt;</span> hey tiny, someone new just walked in

<span class="c"># plans an expressive greeting — all in one turn</span>
<span class="ok">→ reachy_body_turn(30)        rc=0  · turns toward them</span>
<span class="ok">→ reachy_express('curious')   rc=0  · head tilt + antenna perk</span>
<span class="ok">→ reachy_say('oh, hello!')    rc=0  · TTS + wobble</span>

<span class="p">&gt;</span> "oh, hello! nice to meet you."<span class="cur"></span>
</div>

## why it works

Because expression maps to *tools*, the model reasons about **how to feel**,
not just what to say. "Be shy" isn't a canned animation — the model composes
drooped antennas + a downward head tilt + a small body turn away, and narrates
softly. Emergent body language from a language model.
