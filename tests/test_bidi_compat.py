"""tools/bidi_compat is the ONE place TINY touches Strands bidi: it resolves strands.bidi first,
falls back to strands.experimental.bidi, maps 1.20 event names onto 1.57 ones, and ships our own
stop_conversation (1.57.1: request_state flag; strands.bidi main: agent.cancel())."""
import asyncio
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import bidi_compat as c  # noqa: E402


def test_resolves_a_bidi_package_and_the_agent():
    assert c.BIDI_PACKAGE in ("strands.bidi", "strands.experimental.bidi")
    assert c.IS_STABLE == (c.BIDI_PACKAGE == "strands.bidi")
    assert c.BidiAgent.__name__ == "BidiAgent"
    assert c.BidiAgent is importlib.import_module(c.BIDI_PACKAGE).BidiAgent
    for name in ("send", "run", "receive", "start", "stop"):
        assert hasattr(c.BidiAgent, name)


def test_stable_path_is_preferred_when_present():
    """When strands.bidi exists it wins; on 1.57.1 (experimental only) the fallback is taken."""
    try:
        importlib.import_module("strands.bidi")
    except ImportError:
        assert c.BIDI_PACKAGE == "strands.experimental.bidi"
    else:
        assert c.BIDI_PACKAGE == "strands.bidi"


def test_send_types_are_the_core_blocks():
    from strands.types.content import TextBlock
    from strands.types.media import ImageBlock
    assert c.TextBlock is TextBlock and c.ImageBlock is ImageBlock
    d = c.AudioDelta(format="pcm", source={"bytes": b"\x00\x00"})
    assert d.to_dict() == {"audio_delta": {"format": "pcm", "source": {"bytes": b"\x00\x00"}}}
    assert c.TextBlock("hi").to_dict() == {"text": "hi"}


def test_model_classes_resolve_lazily():
    assert c.model_class("openai").__name__ == "OpenAIRealtimeModel"
    assert c.model_class("openai_realtime") is c.model_class("openai")
    assert c.realtime_model_class() is c.model_class("openai")
    for alias in ("nova_sonic", "novasonic", "nova"):
        assert c._MODEL_NAMES[alias][1] == "BedrockNovaSonicModel"
    for alias in ("gemini", "gemini_live"):
        assert c._MODEL_NAMES[alias][1] == "GoogleGeminiLiveModel"
    with pytest.raises(ValueError):
        c.model_class("siri")


def test_events_are_the_1_57_names_and_legacy_maps_onto_them():
    assert c.EVENTS.AUDIO_DELTA == "bidi_audio_delta"
    assert c.EVENTS.BARGE_IN == "bidi_barge_in"
    assert c.EVENTS.RESPONSE_STOP == "bidi_response_stop"
    assert c.EVENTS.CONNECTION_STOP == "bidi_connection_stop"
    assert c.LEGACY_EVENTS["bidi_audio_stream"] == c.EVENTS.AUDIO_DELTA
    assert c.LEGACY_EVENTS["bidi_interruption"] == c.EVENTS.BARGE_IN
    assert c.LEGACY_EVENTS["bidi_response_complete"] == c.EVENTS.RESPONSE_STOP
    assert c.LEGACY_EVENTS["bidi_connection_close"] == c.EVENTS.CONNECTION_STOP
    with pytest.raises(TypeError):
        c.LEGACY_EVENTS["x"] = "y"          # frozen


def test_event_names_exist_in_the_installed_strands():
    """Every EVENTS value is a type string some installed event class emits."""
    ev = importlib.import_module(f"{c.BIDI_PACKAGE}.types.events")
    src = Path(ev.__file__).read_text(encoding="utf-8")
    for name, value in vars(c.EVENTS).items():
        assert f'"{value}"' in src, f"{name}={value} is not emitted by {ev.__file__}"


def test_event_type_normalises_both_vintages():
    assert c.event_type({"type": "bidi_audio_stream"}) == "bidi_audio_delta"
    assert c.event_type({"type": "bidi_audio_delta"}) == "bidi_audio_delta"
    assert c.event_type({"type": "bidi_transcript_stream", "is_final": False}) == "bidi_transcript_delta"
    assert c.event_type({"type": "bidi_transcript_stream", "is_final": True}) == "bidi_transcript_stop"
    assert c.event_type({"type": "bidi_transcript_stop"}) == "bidi_transcript_stop"
    assert c.event_type("not an event") is None
    assert c.transcript_text({"type": "bidi_transcript_stop", "transcript": "hi"}) == "hi"
    assert c.transcript_text({"type": "bidi_transcript_delta", "delta": "h"}) == "h"
    assert c.transcript_text({"type": "bidi_transcript_stream", "is_final": True, "current_transcript": "old"}) == "old"


def test_hooks_namespace():
    from strands.hooks import MessageAddedEvent
    assert c.hooks.MessageAddedEvent is MessageAddedEvent
    hooks = importlib.import_module(f"{c.BIDI_PACKAGE}.hooks")
    assert c.hooks.ResponseStop is hooks.BidiResponseStopEvent
    assert c.hooks.BargeIn is hooks.BidiBargeInEvent
    assert c.hooks.AgentStop is hooks.BidiAgentStopEvent


def test_audio_streams_are_the_private_io_classes():
    pytest.importorskip("pyaudio")
    inp, out, buf = c.audio_streams()
    assert inp.__name__ == "_AudioInputStream" and out.__name__ == "_AudioOutputStream"
    assert buf.__name__ == "AudioBuffer"
    assert c.audio_io_class().__name__ == "AudioIO"


class _Ctx:
    def __init__(self, agent=None):
        self.invocation_state = {}
        self.agent = agent


def test_stop_conversation_sets_the_1_57_flag_and_calls_cancel_when_present():
    class _Agent:
        cancelled = False

        def cancel(self):
            self.cancelled = True

    ctx = _Ctx(_Agent())
    assert c.stop_conversation.tool_spec["name"] == "stop_conversation"
    assert c.stop_conversation._tool_func(ctx) == "Ending conversation"
    assert ctx.invocation_state["request_state"]["stop_event_loop"] is True
    assert ctx.agent.cancelled is True


def test_stop_conversation_without_cancel_is_fine():
    ctx = _Ctx(object())
    assert c.stop_conversation._tool_func(ctx) == "Ending conversation"
    assert ctx.invocation_state["request_state"]["stop_event_loop"] is True


def test_sinks_use_the_compat_names_not_literals():
    """No other module hard-codes a bidi_* event string or imports strands.experimental.bidi."""
    root = Path(__file__).resolve().parents[1]
    offenders = []
    for p in list((root / "tools").glob("*.py")) + [root / "tiny.py", root / "voice_listener.py",
                                                       root / "resampling_audio.py"]:
        if p.name == "bidi_compat.py":
            continue
        src = p.read_text(encoding="utf-8")
        for line in src.splitlines():
            code = line.split("#", 1)[0]
            if ("import" in code and ("strands.experimental.bidi" in code or "strands.bidi" in code)):
                offenders.append(f"{p.name}: imports strands bidi directly: {line.strip()[:80]}")
            if '"bidi_' in code and "EVENTS" not in code:
                offenders.append(f"{p.name}: literal event name: {line.strip()[:80]}")
    assert not offenders, offenders
