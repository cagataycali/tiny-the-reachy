"""Realtime session tuning for the voice persona — what Strands' provider_config
cannot reach (1.20 only forwards voice / sample rates / a few inference keys).

Why: the voice log fills with phantom transcripts in random languages ("שרון",
"よっべ", "Fiecare dată") on room noise — the default server VAD (threshold 0.5)
fires and gpt-4o-transcribe, with no language hint, guesses. Each one costs a
"TINY didn't catch that". We pin the transcription language and raise the VAD
bar, all from env so nothing here is hard-coded per household:

    VOICE_LANG              ISO-639-1 for input transcription (e.g. tr, en). Unset = auto.
    VOICE_VAD_THRESHOLD     server_vad threshold, default 0.6 (OpenAI default 0.5)
    VOICE_VAD_SILENCE_MS    end-of-turn silence, default 600 (OpenAI default 500)
    VOICE_VAD_PREFIX_MS     audio kept before speech onset, default 300

Applied by wrapping BidiOpenAIRealtimeModel._build_session_config (idempotent),
deep-copying the config so the module-level DEFAULT_SESSION_CONFIG is never mutated
(the stock implementation shallow-copies it). No-op for other providers.
"""
from __future__ import annotations

import copy
import os


def _as_float(raw: str, default: float) -> float:
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _as_int(raw: str, default: int) -> int:
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def session_overrides() -> dict:
    """The audio.input overrides we want, from env."""
    turn = {
        "type": "server_vad",
        "threshold": max(0.0, min(1.0, _as_float(os.getenv("VOICE_VAD_THRESHOLD", "0.6"), 0.6))),
        "prefix_padding_ms": _as_int(os.getenv("VOICE_VAD_PREFIX_MS", "300"), 300),
        "silence_duration_ms": _as_int(os.getenv("VOICE_VAD_SILENCE_MS", "600"), 600),
    }
    out: dict = {"turn_detection": turn}
    lang = (os.getenv("VOICE_LANG") or "").strip().lower()
    if lang:
        out["transcription"] = {"model": "gpt-4o-transcribe", "language": lang}
    return out


def apply_session_config(config: dict) -> dict:
    """Return a deep copy of ``config`` with the audio.input overrides merged in."""
    cfg = copy.deepcopy(config)
    inp = cfg.setdefault("audio", {}).setdefault("input", {})
    for key, value in session_overrides().items():
        if isinstance(inp.get(key), dict) and isinstance(value, dict):
            inp[key] = {**inp[key], **value}
        else:
            inp[key] = value
    return cfg


def patch_openai_realtime_session() -> bool:
    """Wrap BidiOpenAIRealtimeModel._build_session_config once. True if patched (or already)."""
    try:
        from .vision import _realtime_model_class
    except ImportError:  # pragma: no cover
        return False
    cls = _realtime_model_class()
    if cls is None:
        return False
    if getattr(cls, "_session_patched", False):
        return True
    orig = cls._build_session_config

    def _patched(self, system_prompt, tools):
        return apply_session_config(orig(self, system_prompt, tools))

    cls._build_session_config = _patched
    cls._session_patched = True
    return True
