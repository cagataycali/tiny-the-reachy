"""One import surface for Strands bidirectional streaming.

TINY runs strands-agents built from harness-sdk MAIN (``scripts/strands_wheel.sh`` pins the
sha), where bidi lives in ``strands.bidi`` (#4707). ``strands.experimental.bidi`` is only a
deprecation shim there (gone in v1.60.0) and is the one place PyPI 1.57.1 still has it; it is
kept as a guarded fallback because it costs five lines, but nothing else in TINY may import
it, and the test suite asserts the stable package is the one in use.

Resolution order: ``strands.bidi`` first, then ``strands.experimental.bidi``.

What this module gives the rest of the code base:

* ``BIDI_PACKAGE``       the dotted package name that was found
* ``BidiAgent``          the agent class
* ``TextBlock`` / ``ImageBlock`` / ``AudioDelta``   what ``agent.send`` accepts (1.57+)
* ``model_class(provider)``  lazy loader for OpenAIRealtimeModel / BedrockNovaSonicModel /
                              GoogleGeminiLiveModel (each pulls optional deps, so never at import)
* ``audio_io_class()``   lazy loader for ``AudioIO`` (needs PyAudio)
* ``audio_streams()``    the private ``_AudioInputStream`` / ``_AudioOutputStream`` /
                              ``AudioBuffer`` trio that ResamplingAudioIO subclasses
* ``hooks``              the bidi hook events + the core ``MessageAddedEvent``
* ``EVENTS``             frozen output-event type strings (``EVENTS.AUDIO_DELTA`` ...)
* ``LEGACY_EVENTS``      1.20 -> 1.57 event-name map, so sinks accept both for one release
* ``stop_conversation``  TINY's own tool: ``tool_context.agent.cancel()`` (#4664; the stock
                              tool and the 1.57.1 ``request_state["stop_event_loop"]`` flag
                              are both gone on main)
* ``event_type(event)``  the normalised (new-style) type string of any output event
"""
from __future__ import annotations

import importlib
from types import MappingProxyType, SimpleNamespace
from typing import Any

from strands import tool
from strands.hooks import MessageAddedEvent

try:
    from strands.types.content import TextBlock
    from strands.types.media import ImageBlock
except ImportError as _e:  # strands-agents < 1.57: BidiTextInputEvent era, dropped on purpose
    raise ImportError(
        "TINY's voice persona needs strands-agents[bidi]>=1.57.2.dev0,<1.60 built from harness-sdk main "
        "(scripts/strands_wheel.sh; agent.send(TextBlock|ImageBlock), agent.cancel()); "
        "see MIGRATION.md for the robot upgrade recipe"
    ) from _e

_CANDIDATES = ("strands.bidi", "strands.experimental.bidi")


def _resolve_package() -> tuple[Any, str]:
    last: Exception | None = None
    for name in _CANDIDATES:
        try:
            return importlib.import_module(name), name
        except ImportError as e:  # pragma: no cover - depends on the installed strands
            last = e
    raise ImportError(
        "no Strands bidi package found (tried strands.bidi, strands.experimental.bidi); "
        "build strands-agents from harness-sdk main with scripts/strands_wheel.sh"
    ) from last


_bidi, BIDI_PACKAGE = _resolve_package()
IS_STABLE = BIDI_PACKAGE == "strands.bidi"


def _sub(name: str):
    return importlib.import_module(f"{BIDI_PACKAGE}.{name}")


BidiAgent = _bidi.BidiAgent
AudioDelta = _sub("types.media").AudioDelta
_hooks_mod = _sub("hooks")

hooks = SimpleNamespace(
    MessageAddedEvent=MessageAddedEvent,
    ResponseStop=_hooks_mod.BidiResponseStopEvent,
    BargeIn=_hooks_mod.BidiBargeInEvent,
    AgentStop=_hooks_mod.BidiAgentStopEvent,
    BeforeConnectionRestart=_hooks_mod.BidiBeforeConnectionRestartEvent,
    AfterConnectionRestart=_hooks_mod.BidiAfterConnectionRestartEvent,
)

# ── output event type strings (1.57+) ──────────────────────────────────────
EVENTS = SimpleNamespace(
    CONNECTION_START="bidi_connection_start",
    CONNECTION_RESTART="bidi_connection_restart",
    CONNECTION_WARNING="bidi_connection_warning",
    CONNECTION_STOP="bidi_connection_stop",
    RESPONSE_START="bidi_response_start",
    RESPONSE_STOP="bidi_response_stop",
    AUDIO_START="bidi_audio_start",
    AUDIO_DELTA="bidi_audio_delta",
    AUDIO_STOP="bidi_audio_stop",
    TRANSCRIPT_START="bidi_transcript_start",
    TRANSCRIPT_DELTA="bidi_transcript_delta",
    TRANSCRIPT_STOP="bidi_transcript_stop",
    BARGE_IN="bidi_barge_in",
    USAGE="bidi_usage",
)

# 1.20 name -> 1.57 name. Kept for one release so a sink fed by an older peer still works.
LEGACY_EVENTS = MappingProxyType({
    "bidi_audio_stream": EVENTS.AUDIO_DELTA,
    "bidi_transcript_stream": EVENTS.TRANSCRIPT_DELTA,   # is_final=True variants map to TRANSCRIPT_STOP in event_type()
    "bidi_response_complete": EVENTS.RESPONSE_STOP,
    "bidi_interruption": EVENTS.BARGE_IN,
    "bidi_connection_close": EVENTS.CONNECTION_STOP,
})

#: 1.20 names that had no 1.57 twin: the agent now raises errors instead of streaming them.
LEGACY_ERROR_EVENT = "bidi_error"


def event_type(event: Any) -> str | None:
    """Normalised type of an output event: new-style names for both 1.20 and 1.57 shapes."""
    if not isinstance(event, dict):
        return None
    t = event.get("type")
    if t == "bidi_transcript_stream" and event.get("is_final"):
        return EVENTS.TRANSCRIPT_STOP
    return LEGACY_EVENTS.get(t, t)


def transcript_text(event: dict) -> str:
    """The text carried by a transcript event, whatever its vintage."""
    if event.get("type") == "bidi_transcript_stream":
        return str(event.get("current_transcript") or event.get("text") or "")
    return str(event.get("transcript") if "transcript" in event else event.get("delta") or "")


# ── lazy loaders (optional deps) ───────────────────────────────────────────
_MODEL_NAMES = {
    "openai": ("models.openai", "OpenAIRealtimeModel"),
    "openai_realtime": ("models.openai", "OpenAIRealtimeModel"),
    "nova_sonic": ("models.bedrock", "BedrockNovaSonicModel"),
    "novasonic": ("models.bedrock", "BedrockNovaSonicModel"),
    "nova": ("models.bedrock", "BedrockNovaSonicModel"),
    "gemini": ("models.google", "GoogleGeminiLiveModel"),
    "gemini_live": ("models.google", "GoogleGeminiLiveModel"),
}

PROVIDERS = ("openai", "nova_sonic", "gemini")


def model_class(provider: str):
    """The bidi model class for a provider name (raises ValueError for an unknown one)."""
    key = provider.lower()
    if key not in _MODEL_NAMES:
        raise ValueError(f"unknown voice provider: {provider}")
    mod, cls = _MODEL_NAMES[key]
    return getattr(_sub(mod), cls)


def realtime_model_class():
    """OpenAIRealtimeModel, or None when its optional deps (websockets) are missing."""
    try:
        return model_class("openai")
    except ImportError:
        return None


def audio_io_class():
    """``AudioIO`` (PyAudio-backed local mic + speaker)."""
    return _sub("io.audio").AudioIO


def audio_streams():
    """(_AudioInputStream, _AudioOutputStream, AudioBuffer) for subclassing."""
    audio = _sub("io.audio")
    buffer = _sub("_audio.buffer")
    return audio._AudioInputStream, audio._AudioOutputStream, buffer.AudioBuffer


# ── stop_conversation ──────────────────────────────────────────────────────
# Built with tool(...)(fn), not @tool: this is Strands session plumbing (the stock tool it
# replaces was never one of TINY's documented abilities), so scripts/tooldoc.py and the
# landing's tool wall keep counting TINY's own tools only.
def _stop_conversation(tool_context) -> str:
    """End the voice session.

    Use ONLY when the user says "stop conversation" or clearly asks TINY to end the voice
    session. Do NOT use for "stop", "goodbye", "bye" or other farewells or phrases.
    """
    # strands.bidi (main, #4664): BidiAgent.cancel() sets a thread-safe signal the event loop
    # honours after the current tool group completes. The 1.57.1 request_state["stop_event_loop"]
    # flag does not exist on main, so it is not set here (1.57.1 is not a supported target).
    agent = getattr(tool_context, "agent", None)
    cancel = getattr(agent, "cancel", None)
    if not callable(cancel):
        return "Cannot end the conversation: this agent has no cancel() (strands.bidi main is required)"
    cancel()
    return "Ending conversation"


stop_conversation = tool(name="stop_conversation", context=True)(_stop_conversation)


__all__ = [
    "AudioDelta", "BIDI_PACKAGE", "BidiAgent", "EVENTS", "ImageBlock", "IS_STABLE",
    "LEGACY_ERROR_EVENT", "LEGACY_EVENTS", "PROVIDERS", "TextBlock", "audio_io_class",
    "audio_streams", "event_type", "hooks", "model_class", "realtime_model_class",
    "stop_conversation", "transcript_text",
]
