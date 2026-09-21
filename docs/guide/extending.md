---
title: Extending
description: "Adding a robot capability is a three-step pattern — write the @tool, export it into the bundle, prove it imports without hardware — plus the SDK surface the existing tools already trust."
for: tool authors
proof: code
verified: 2026-09-21
---

# Extending

!!! abstract "In 10 seconds"
    - Write `tools/reachy_something.py` with `@tool`, `get_mini()`, `clamp()`, and return `ok()` / `err()` — never raise.
    - Export it in `tools/__init__.py` and append it to the right `TINY_*_TOOLS` list; every persona picks it up through `build_tools()`.
    - `make test-tools` (= `tests/test_import.py`) proves it imports and registers with no robot; the docs regenerate its page at the next build.
    - The docstring *is* the documentation: the model reads it, and `scripts/tooldoc.py` renders it — write `Args:` / `Examples:` sections.

## 1. Write the tool

```python
# tools/reachy_something.py
from strands import tool
from ._reachy_common import get_mini, clamp, ok, err

@tool
def reachy_something(param: float = 0.0) -> dict:
    """One-line intent the LLM reads to decide when to call this."""
    try:
        mini = get_mini()          # cached singleton — never re-connect
        mini.some_sdk_method(param)
        return ok(f"did something with {param}")
    except Exception as e:
        return err(f"reachy_something failed: {e}")
```

!!! danger "Always use `get_mini()`"
    Never construct `ReachyMini()` yourself. `get_mini()` returns a **cached
    singleton** — re-connecting fights the daemon and causes flaky control.

## 2. Export and bundle it

```python
# tools/__init__.py
from .reachy_something import reachy_something

TINY_MOTION_TOOLS = [
    reachy_look, reachy_antennas, reachy_body_turn,
    reachy_home, reachy_wake,
    reachy_something,          # ← add to the right bundle
]
```

## 3. Smoke test (no robot needed)

```bash
make test-tools    # imports + registers every tool + checks prompts + clamps
```

`tests/test_import.py` proves everything imports and registers cleanly without
any hardware. Run it first, always.

## Verified SDK surface

The tools rely on these `reachy_mini` SDK methods (`requirements.txt`: `reachy_mini[opencv,examples]`; the robot runs daemon 1.10, the
list was confirmed against 1.9 and nothing in it changed):

```
goto_target · set_target · wake_up · goto_sleep
get_current_head_pose · get_current_joint_positions
enable_motors · disable_motors · enable_gravity_compensation
look_at_image · play_move · enable_wobbling
media.get_frame · media.play_sound · imu
RecordedMoves.list_moves()   # emotion catalogue
```

## Use the helpers

`_reachy_common` gives you `ok(msg)` / `err(msg)` for consistent tool returns
and `clamp(v, lo, hi)` for the safety envelope. Use them — every existing tool
does, and it keeps returns uniform for the model to parse.
