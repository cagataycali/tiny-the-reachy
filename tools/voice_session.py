"""Realtime session tuning for the voice persona: OpenAI ``session.update`` keys that
Strands' constructor does not expose as keywords (VAD, transcription language/prompt).

Why: the voice log fills with phantom transcripts in random languages ("שרון",
"よっべ", "Fiecare dată") on room noise — the default server VAD (threshold 0.5)
fires and gpt-4o-transcribe, with no language hint, guesses. Each one costs a
"TINY didn't catch that". We pin the transcription language and raise the VAD
bar, all from env so nothing here is hard-coded per household:

    VOICE_LANG              ISO-639-1 for input transcription (e.g. tr, en). Unset = auto.
    VOICE_TRANSCRIBE_PROMPT free-text hint for the transcriber ("Turkish or English, robot named TINY")
    VOICE_TURN_DETECTION    server_vad (default) | semantic_vad
    VOICE_VAD_THRESHOLD     server_vad threshold, default 0.5 (= OpenAI). Raising it makes barge-in
                            over TINY's own speech HARDER — the XMOS board's hardware AEC already
                            removes the echo, so there is no reason to.
    VOICE_VAD_SILENCE_MS    end-of-turn silence, default 600 (OpenAI default 500)
    VOICE_VAD_PREFIX_MS     audio kept before speech onset, default 300
    VOICE_VAD_EAGERNESS     semantic_vad only: low | medium | high | auto
interrupt_response / create_response are always set true (barge-in is the server's job).

Applied NATIVELY on Strands 1.57+: ``session_params()`` is passed as
``OpenAIRealtimeModel(params=...)`` and ``_build_session_config`` deep-merges it over
DEFAULT_SESSION_CONFIG (``_merge_config``), so no monkey patch and no mutation of the
module default. ``apply_session_config`` does the same merge on a plain dict (tests,
and the one assertion the model makes on strands.bidi main: turn_detection must carry
create_response=True and interrupt_response=True or the constructor-time build raises).
No-op for other providers.
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
    kind = (os.getenv("VOICE_TURN_DETECTION", "server_vad") or "server_vad").strip().lower()
    if kind == "semantic_vad":
        eager = (os.getenv("VOICE_VAD_EAGERNESS", "auto") or "auto").strip().lower()
        if eager not in ("low", "medium", "high", "auto"):
            eager = "auto"
        turn: dict = {"type": "semantic_vad", "eagerness": eager}
    else:
        turn = {
            "type": "server_vad",
            "threshold": max(0.0, min(1.0, _as_float(os.getenv("VOICE_VAD_THRESHOLD", "0.5"), 0.5))),
            "prefix_padding_ms": _as_int(os.getenv("VOICE_VAD_PREFIX_MS", "300"), 300),
            "silence_duration_ms": _as_int(os.getenv("VOICE_VAD_SILENCE_MS", "600"), 600),
        }
    # Barge-in is a server decision on Realtime: speech_started must cancel the
    # in-flight response and the end of the user's turn must start a new one.
    turn["interrupt_response"] = True
    turn["create_response"] = True
    out: dict = {"turn_detection": turn}
    transcription: dict = {"model": "gpt-4o-transcribe"}
    lang = (os.getenv("VOICE_LANG") or "").strip().lower()
    if lang:
        transcription["language"] = lang
    hint = (os.getenv("VOICE_TRANSCRIBE_PROMPT") or "").strip()
    if hint:
        transcription["prompt"] = hint
    if len(transcription) > 1:
        out["transcription"] = transcription
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


def session_params() -> dict:
    """The ``params`` keyword for ``OpenAIRealtimeModel``: our audio.input overrides."""
    return {"audio": {"input": session_overrides()}}


def session_config_is_valid(config: dict) -> bool:
    """The check strands.bidi (main) performs before connecting: barge-in keys present and true."""
    turn = (config.get("audio") or {}).get("input", {}).get("turn_detection")
    return bool(turn) and bool(turn.get("create_response", True)) and bool(turn.get("interrupt_response", True))
