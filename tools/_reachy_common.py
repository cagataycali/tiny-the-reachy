"""Shared ReachyMini connection + helpers for all TINY @tool wrappers.

Mirrors neon's tools/_g1_common.py pattern: ONE cached singleton client,
never re-connect per tool call. The daemon owns the hardware; we're a client
talking to it over the WS/REST surface (localhost:8000 on Lite, or
reachy-mini.local:8000 on Wireless).

Safety limits (SDK clamps, but we surface them):
    head pitch/roll : [-40, +40] deg
    head yaw        : [-180, +180] deg
    body yaw        : [-160, +160] deg
    yaw delta (head-body) : max 65 deg
"""
import os
import threading
from typing import Optional

_LOCK = threading.Lock()
_MINI = None  # cached ReachyMini singleton

# Connection knobs (env-overridable, work out-of-the-box for Lite dev)
HOST = os.getenv("REACHY_HOST", "reachy-mini.local")
PORT = int(os.getenv("REACHY_PORT", "8000"))
CONNECTION_MODE = os.getenv("REACHY_CONNECTION_MODE", "auto")  # auto | localhost_only | network
USE_SIM = os.getenv("REACHY_USE_SIM", "").lower() in ("1", "true", "yes")
SPAWN_DAEMON = os.getenv("REACHY_SPAWN_DAEMON", "").lower() in ("1", "true", "yes")
# "no_media" keeps the daemon owning camera/mic so multiple personas can share
# it; personas that need frames pull them from the shared camera proxy.
MEDIA_BACKEND = os.getenv("REACHY_MEDIA_BACKEND", "no_media")

# Safety envelope (degrees)
LIM_HEAD_PITCH = (-40.0, 40.0)
LIM_HEAD_ROLL = (-40.0, 40.0)
LIM_HEAD_YAW = (-180.0, 180.0)
LIM_BODY_YAW = (-160.0, 160.0)
MAX_YAW_DELTA = 65.0


def get_mini(media_backend: Optional[str] = None):
    """Return the cached ReachyMini client, connecting on first use.

    Idempotent + thread-safe. Raises RuntimeError with a friendly message if
    the daemon isn't reachable so tools can surface it cleanly to the LLM.
    """
    global _MINI
    with _LOCK:
        if _MINI is not None:
            return _MINI
        try:
            from reachy_mini import ReachyMini
        except Exception as e:  # pragma: no cover - import guard
            raise RuntimeError(
                f"reachy_mini SDK not importable: {e}. "
                f"pip install reachy_mini (see requirements.txt)."
            )
        try:
            _MINI = ReachyMini(
                host=HOST,
                port=PORT,
                connection_mode=CONNECTION_MODE,
                use_sim=USE_SIM,
                spawn_daemon=SPAWN_DAEMON,
                media_backend=media_backend or MEDIA_BACKEND,
                automatic_body_yaw=True,
            )
        except Exception as e:
            raise RuntimeError(
                f"Could not connect to Reachy Mini daemon at {HOST}:{PORT} "
                f"(mode={CONNECTION_MODE}): {e}. Is the daemon running? "
                f"Lite: localhost:8000 | Wireless: reachy-mini.local:8000. "
                f"Set REACHY_USE_SIM=1 to run against MuJoCo simulation."
            )
        return _MINI


def reset_mini():
    """Drop the cached client (forces reconnect next call). For error recovery."""
    global _MINI
    with _LOCK:
        try:
            if _MINI is not None:
                _MINI.client.disconnect()
        except Exception:
            pass
        _MINI = None


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def ok(text: str, **extra) -> dict:
    d = {"status": "success", "content": [{"text": text}]}
    if extra:
        d["content"].append({"json": extra})
    return d


def err(text: str) -> dict:
    return {"status": "error", "content": [{"text": text}]}
