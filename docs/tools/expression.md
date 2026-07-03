# expression

<span class="read-badge">⏱ 45s</span>

TINY has no arms and no legs. **Expression *is* the personality.** Beyond raw
head/antenna/body moves, TINY has a library of pre-recorded emotions and
dances — the equivalent of neon's arm-gesture playbook.

## `reachy_express` — play a named emotion

```python
reachy_express(emotion="happy",
               initial_goto_duration=1.0)
```

Plays a recorded move from
[`pollen-robotics/reachy-mini-emotions-library`](https://huggingface.co/pollen-robotics/reachy-mini-emotions-library).
The library is **downloaded live on first use** (cached afterwards), so the
first call may take a moment.

```
"be happy"      → reachy_express('happy')
"say no"        → reachy_express('no')       (head shake)
"you're curious"→ reachy_express('curious')
"act surprised" → reachy_express('surprised')
```

## `reachy_list_emotions` — discover the library

```python
reachy_list_emotions()   # → every available move name
```

Call this when you're unsure what's available, then pick the closest match.
The catalogue comes from `RecordedMoves.list_moves()` in the SDK.

## fire expression *with* speech

The golden rule (from `prompts/base.md`): expressions happen **simultaneously**
with speech, never before or after. In practice the model batches the calls:

```python
# "hi there!" — spoken AND expressed at once
reachy_say("hi there!")        # TTS + head-wobble
reachy_express("happy")        # antenna wiggle + head bob
```

See the [expression showcase](../showcase/expression.md) for the full playbook.
