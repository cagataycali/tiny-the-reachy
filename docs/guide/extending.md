# extending

<span class="read-badge">⏱ 60s</span>

Adding a new robot capability is a three-step pattern — the same one neon uses.

## 1 · write the tool

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

## 2 · export & bundle it

```python
# tools/__init__.py
from .reachy_something import reachy_something

TINY_MOTION_TOOLS = [
    reachy_look, reachy_antennas, reachy_body_turn,
    reachy_home, reachy_wake,
    reachy_something,          # ← add to the right bundle
]
```

## 3 · smoke test (no robot needed)

```bash
make test-tools    # imports + registers every tool + checks prompts + clamps
```

`tests/test_import.py` proves everything imports and registers cleanly without
any hardware. Run it first, always.

## verified SDK surface (1.9)

The tools rely on these confirmed methods:

```
goto_target · set_target · wake_up · goto_sleep
get_current_head_pose · get_current_joint_positions
enable_motors · disable_motors · enable_gravity_compensation
look_at_image · play_move · enable_wobbling
media.get_frame · media.play_sound · imu
RecordedMoves.list_moves()   # emotion catalogue
```

## use the helpers

`_reachy_common` gives you `ok(msg)` / `err(msg)` for consistent tool returns
and `clamp(v, lo, hi)` for the safety envelope. Use them — every existing tool
does, and it keeps returns uniform for the model to parse.
