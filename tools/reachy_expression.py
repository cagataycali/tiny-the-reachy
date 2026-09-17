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


# Plain-English → library name. The HF library (81 moves as of 2026-09-17) has NO bare "happy"/
# "curious"/"no": every move carries a take number (cheerful1, curious1, no1 …). Before this map
# the prompts' natural names produced 125 "emotion 'x' not found" tool errors in the agent log and a
# wasted retry round-trip per gesture (the voice persona pays that in latency).
EMOTION_ALIASES = {
    "happy": "cheerful1", "joy": "cheerful1", "glad": "cheerful1", "cheerful": "cheerful1",
    "excited": "enthusiastic1", "enthusiastic": "enthusiastic1", "hello": "welcoming1", "welcome": "welcoming1",
    "greeting": "welcoming1", "curious": "curious1", "surprised": "surprised1", "amazed": "amazed1",
    "yes": "yes1", "nod": "yes1", "no": "no1", "shake": "no1", "sad": "sad1", "angry": "rage1", "mad": "furious1",
    "scared": "scared1", "afraid": "fear1", "tired": "tired1", "sleepy": "tired1", "sleep": "sleep1",
    "bored": "boredom1", "confused": "confused1", "thinking": "thoughtful1", "thoughtful": "thoughtful1",
    "shy": "shy1", "proud": "proud1", "grateful": "grateful1", "thanks": "grateful1", "love": "loving1",
    "loving": "loving1", "laugh": "laughing1", "laughing": "laughing1", "oops": "oops1", "sorry": "oops1",
    "relief": "relief1", "relieved": "relief1", "calm": "calming1", "serene": "serenity1", "lonely": "lonely1",
    "success": "success1", "win": "success1", "dance": "dance1", "attentive": "attentive1", "listening": "attentive1",
    "helpful": "helpful1", "impatient": "impatient1", "irritated": "irritated1", "frustrated": "frustrated1",
    "disgusted": "disgusted1", "uncertain": "uncertain1", "understanding": "understanding1", "come": "come1",
    "go_away": "go_away1", "go away": "go_away1", "lost": "lost1", "exhausted": "exhausted1", "electric": "electric1",
}


def resolve_emotion(name: str, names=None) -> Optional[str]:
    """Map a requested emotion to a real library move name, or None.

    Order: exact → alias table → name+"1" → unique prefix match (e.g. "displeased" → displeased1).
    Pure function so it is unit-testable without the SDK; `names` defaults to the cached catalogue.
    """
    names = list(names if names is not None else _MOVE_NAMES)
    key = (name or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not key:
        return None
    if key in names:
        return key
    alias = EMOTION_ALIASES.get(key) or EMOTION_ALIASES.get(key.replace("_", " "))
    if alias and (alias in names or not names):
        return alias
    if key + "1" in names:
        return key + "1"
    hits = sorted(n for n in names if n.startswith(key))
    return hits[0] if hits else None


def _hold_tracking(name: str, on: bool, ttl: float = 12.0) -> None:
    try:
        from .head_tracking import tracking_hold  # noqa: PLC0415
        tracking_hold(name, on, ttl)
    except Exception:  # noqa: BLE001 — never let tracking plumbing break an emotion
        pass


@tool
def reachy_express(emotion: str = "happy", initial_goto_duration: float = 1.0,
                   sound: bool = True) -> dict:
    """Play a named emotion/dance from TINY's recorded-move library. USE PROACTIVELY.

    This is the primary way TINY shows personality — a full head+antenna+body
    choreography (optionally with synced sound). Call it alongside speaking,
    just like neon fires arm gestures.

    Plain names resolve to library moves: happy→cheerful1, curious→curious1, yes→yes1, no→no1,
    surprised→surprised1, sad→sad1, angry→rage1 … (alias table + name+"1" + prefix match).
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
        resolved = resolve_emotion(emotion) or emotion
        try:
            move = moves.get(resolved)
        except Exception:
            avail = ", ".join(_MOVE_NAMES[:40]) if _MOVE_NAMES else "(unknown)"
            return err(f"emotion '{emotion}' not found. Available: {avail}")
        mini = get_mini()
        # daemon face tracking (1.10) at weight 1 overrides moves → pause it for the move, resume after
        _hold_tracking(f"emotion:{resolved}", True, ttl=12.0)
        mini.play_move(move, initial_goto_duration=initial_goto_duration, sound=sound)
        _hold_tracking(f"emotion:{resolved}", False)
        note = f" (for '{emotion}')" if resolved != emotion else ""
        return ok(f"expressed '{resolved}'{note}")
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
