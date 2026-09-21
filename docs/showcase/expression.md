---
title: Expression — every answer moves
description: "TINY is not a chatbot with a body bolted on. The golden rule from prompts/base.md, one full turn as it really runs, and why body language emerges from a language model."
for: anyone who wants to understand what makes TINY feel alive
proof: code
verified: 2026-09-21
---

# Expression — every answer moves

!!! abstract "In 10 seconds"
    - The rule: gestures fire **in the same turn as speech** — the antenna wiggle lands on the word "hi", not two seconds later.
    - Expression maps to tools, so the model reasons about *how to feel*; "be shy" is composed, not a canned clip.
    - Recipes per feeling: [tool playbook](../tools/playbook.md) · the 81 recorded takes: `reachy_list_emotions`.

> Gestures happen **simultaneously** with speech — never before, never after.
> <cite>`prompts/base.md`</cite>

The model batches `reachy_express` and `reachy_say` in one turn.

## A full turn

<div class="terminal" markdown>
<span class="p">&gt;</span> hey tiny, someone new just walked in

<span class="c"># plans an expressive greeting — all in one turn</span>

<span class="ok">→ reachy_body_turn(30)        rc=0  · turns toward them</span>

<span class="ok">→ reachy_express('curious')   rc=0  · head tilt + antenna perk</span>

<span class="ok">→ reachy_say('oh, hello!')    rc=0  · TTS + wobble</span>

<span class="p">&gt;</span> "oh, hello! nice to meet you."<span class="cur"></span>
</div>

## Why it works

"Be shy" is not a canned animation — the model composes drooped antennas, a downward tilt, a small turn away, and narrates softly. Emergent body language from a language model.
