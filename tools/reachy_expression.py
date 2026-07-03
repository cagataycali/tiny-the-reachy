"""TINY expression tools — the recorded-emotion library (the 'gesture playbook').

Reachy Mini's personality lives in the HF emotions library
(pollen-robotics/reachy-mini-emotions-library): pre-recorded head+antenna+body
choreographies with synced sound. This is TINY's equivalent of neon's
g1_arm_action gesture playbook.

The library is lazily downloaded+cached on first use via RecordedMoves.
"""
from typing import Optional
from strands import tool
from ._reachy_common import get_mini, ok, err

_MOVES = None          # cached RecordedMoves
_MOVE_NAMES: list = []  # cached list of available emotion names
EMOTIONS_REPO = "pollen-robotics/reachy-mini-emotions-library"


def _load_moves():
    global _MOVES, _MOVE_NAMES
    if _MOVES is not None:
        return _MOVES
    from reachy_mini.motion.recorded_move import RecordedMoves
    _MOVES = RecordedMoves(EMOTIONS_REPO)
    try:
        # RecordedMoves.list_moves() returns the catalogue of move names.
        names = _MOVES.list_moves() if hasattr(_MOVES, "list_moves") else []
        _MOVE_NAMES = list(names) if names else []
    except Exception:
        _MOVE_NAMES = []
    return _MOVES


@tool
def reachy_express(emotion: str = "happy", initial_goto_duration: float = 1.0,
                   sound: bool = True) -> dict:
    """Play a named emotion/dance from TINY's recorded-move library. USE PROACTIVELY.

    This is the primary way TINY shows personality — a full head+antenna+body
    choreography (optionally with synced sound). Call it alongside speaking,
    just like neon fires arm gestures.

    Common emotion names (varies by library version — use reachy_list_emotions
    to see the live catalogue): happy, sad, curious, surprised, angry, yes,
    no, dance1, confused, excited, sleepy, greeting.

    Args:
        emotion: name of the recorded move.
        initial_goto_duration: smooth ramp into the move's start pose (s).
        sound: play the move's synced sound if it has one.

    Examples:
        reachy_express("happy")          # greeting / positive
        reachy_express("curious")        # someone new appeared
        reachy_express("no", sound=False) # silent head-shake
    """
    try:
        moves = _load_moves()
        try:
            move = moves.get(emotion)
        except Exception:
            avail = ", ".join(_MOVE_NAMES[:40]) if _MOVE_NAMES else "(unknown)"
            return err(f"emotion '{emotion}' not found. Available: {avail}")
        mini = get_mini()
        mini.play_move(move, initial_goto_duration=initial_goto_duration, sound=sound)
        return ok(f"expressed '{emotion}'")
    except Exception as e:
        return err(f"reachy_express failed: {e}")


@tool
def reachy_list_emotions() -> dict:
    """List all emotion/move names available in TINY's recorded-move library."""
    try:
        _load_moves()
        if not _MOVE_NAMES:
            return ok("library loaded but names could not be enumerated; "
                      "try common names: happy, sad, curious, surprised, yes, no")
        return ok(f"{len(_MOVE_NAMES)} emotions available", emotions=_MOVE_NAMES)
    except Exception as e:
        return err(f"reachy_list_emotions failed: {e}")
