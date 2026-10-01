"""take_photo sends the frame and the question as ONE user message
(agent.send([ImageBlock, TextBlock]), strands.bidi); on the wire the OpenAI model makes one
conversation.item.create and at most one response.create, deferred while the user is speaking
(#4642). The session tuning pins language / VAD from env via the model's native `params` and
never mutates Strands' module-level default config."""
import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import vision  # noqa: E402
from tools import voice_session  # noqa: E402


class _Agent:
    def __init__(self):
        self.sent = []

    async def send(self, content):
        self.sent.append(content)


def test_inject_is_one_message_image_then_question_through_agent_send():
    agent = _Agent()
    asyncio.run(vision._inject(agent, b"AAA", "what do you see?"))
    assert len(agent.sent) == 1 and isinstance(agent.sent[0], list)
    img, text = agent.sent[0]
    assert type(img).__name__ == "ImageBlock" and type(text).__name__ == "TextBlock"
    assert img.format == "jpeg" and img.source == {"bytes": b"AAA"}
    assert text.text == "what do you see?"


class _Wire:
    """A started OpenAIRealtimeModel with the websocket replaced by a recorder (real _SessionState)."""

    def __init__(self, cls):
        self.events = []
        self.model = cls(model_id="gpt-realtime-2", transcription_model_id="gpt-4o-transcribe", api_key="sk-test")
        self.model._connection_id = "test-conn"

        async def _send_event(event):
            self.events.append(event)
        self.model._send_event = _send_event

    @property
    def state(self):
        return self.model._session_state

    def types(self):
        return [e["type"] for e in self.events]

    def send_photo(self, question="what do you see?"):
        import importlib
        BidiMessage = importlib.import_module("strands.bidi.types.content").BidiMessage
        from strands.types.content import TextBlock
        from strands.types.media import ImageBlock
        # exactly what BidiAgent.send([ImageBlock, TextBlock]) hands to the model
        asyncio.run(self.model.send(BidiMessage(content=[ImageBlock(format="jpeg", source={"bytes": b"AAA"}),
                                                         TextBlock(question)])))


def _wire():
    cls = vision._realtime_model_class()
    if cls is None:
        pytest.skip("no Realtime model class in this env")
    assert not hasattr(vision, "_patch_openai_image_support"), "the 1.20 monkey patch must be gone"
    return _Wire(cls)


def test_openai_wire_is_one_item_and_exactly_one_response_create():
    w = _wire()
    w.send_photo()
    assert w.types() == ["conversation.item.create", "response.create"]
    item = w.events[0]["item"]
    assert item["role"] == "user" and [c["type"] for c in item["content"]] == ["input_image", "input_text"]
    assert item["content"][0]["image_url"].startswith("data:image/jpeg;base64,")
    assert item["content"][1]["text"] == "what do you see?"
    assert w.state.response_requested is True and w.state.response_pending is False
    assert w.state.pending_input_ids == set()


def test_openai_wire_defers_response_create_while_the_user_is_speaking():
    """#4642: speech_started sets input_audio_pending; the item goes out, the response.create waits."""
    w = _wire()
    w.state.input_audio_pending = True
    w.send_photo()
    assert w.types() == ["conversation.item.create"], "response.create must be deferred during user speech"
    assert w.state.response_pending is True and w.state.response_requested is False
    assert len(w.state.pending_input_ids) == 1
    # speech ends: the receive loop clears the flag (committed -> VAD owns that response) or, if
    # no VAD response comes, the next flush sends exactly one response.create
    w.state.input_audio_pending = False
    asyncio.run(w.model._flush_response_request(w.state))
    assert w.types() == ["conversation.item.create", "response.create"]
    asyncio.run(w.model._flush_response_request(w.state))
    assert w.types().count("response.create") == 1


def test_openai_wire_never_doubles_a_response_while_one_is_active():
    """A photo while TINY is still answering: the item is appended, the response is coalesced."""
    w = _wire()
    w.state.active_responses.add("resp_1")
    w.send_photo()
    assert w.types() == ["conversation.item.create"]
    assert w.state.response_pending is True
    # response.done for resp_1 -> the model's receive loop would flush; emulate that step
    w.state.active_responses.clear()
    asyncio.run(w.model._flush_response_request(w.state))
    assert w.types().count("response.create") == 1


def test_take_photo_has_a_default_question():
    assert vision.DEFAULT_QUESTION.strip()
    assert "LOOK" in (vision.take_photo.tool_spec["description"])


def test_session_overrides_from_env(monkeypatch):
    monkeypatch.setenv("VOICE_LANG", "tr")
    monkeypatch.setenv("VOICE_VAD_THRESHOLD", "0.7")
    base = {"type": "realtime", "audio": {"input": {"format": {"type": "audio/pcm", "rate": 24000},
                                                   "transcription": {"model": "gpt-4o-transcribe"},
                                                   "turn_detection": {"type": "server_vad", "threshold": 0.5}}}}
    out = voice_session.apply_session_config(base)
    assert out["audio"]["input"]["transcription"] == {"model": "gpt-4o-transcribe", "language": "tr"}
    assert out["audio"]["input"]["turn_detection"]["threshold"] == 0.7
    assert out["audio"]["input"]["turn_detection"]["silence_duration_ms"] == 600
    assert out["audio"]["input"]["format"]["rate"] == 24000
    # the input dict we were given is untouched (Strands shallow-copies its module default)
    assert base["audio"]["input"]["turn_detection"]["threshold"] == 0.5
    assert "language" not in base["audio"]["input"]["transcription"]


def test_no_lang_means_auto(monkeypatch):
    monkeypatch.delenv("VOICE_LANG", raising=False)
    monkeypatch.delenv("VOICE_VAD_THRESHOLD", raising=False)
    out = voice_session.apply_session_config({"audio": {"input": {"transcription": {"model": "gpt-4o-transcribe"}}}})
    assert out["audio"]["input"]["transcription"] == {"model": "gpt-4o-transcribe"}
    assert out["audio"]["input"]["turn_detection"]["threshold"] == 0.5
    assert out["audio"]["input"]["turn_detection"]["interrupt_response"] is True


def test_bad_env_values_fall_back(monkeypatch):
    monkeypatch.setenv("VOICE_VAD_THRESHOLD", "loud")
    monkeypatch.setenv("VOICE_VAD_SILENCE_MS", "x")
    o = voice_session.session_overrides()["turn_detection"]
    assert o["threshold"] == 0.5 and o["silence_duration_ms"] == 600


def test_semantic_vad_and_transcribe_prompt(monkeypatch):
    monkeypatch.setenv("VOICE_TURN_DETECTION", "semantic_vad")
    monkeypatch.setenv("VOICE_VAD_EAGERNESS", "loud")
    monkeypatch.setenv("VOICE_TRANSCRIBE_PROMPT", "Turkish or English, talking to a robot named TINY")
    monkeypatch.delenv("VOICE_LANG", raising=False)
    o = voice_session.session_overrides()
    assert o["turn_detection"] == {"type": "semantic_vad", "eagerness": "auto",
                                   "interrupt_response": True, "create_response": True}
    assert o["transcription"]["prompt"].startswith("Turkish")
    assert "language" not in o["transcription"]


def test_session_params_merge_natively_and_pass_the_barge_in_check(monkeypatch):
    """OpenAIRealtimeModel(params=session_params()) is deep-merged over DEFAULT_SESSION_CONFIG by
    _build_session_config; the result must carry our VAD and the create/interrupt flags strands.bidi
    main refuses to connect without."""
    cls = vision._realtime_model_class()
    if cls is None:
        pytest.skip("no Realtime model class in this env")
    monkeypatch.setenv("VOICE_LANG", "tr")
    monkeypatch.setenv("VOICE_VAD_THRESHOLD", "0.7")
    m = cls(model_id="gpt-realtime-2", voice="shimmer", transcription_model_id="gpt-4o-transcribe",
            api_key="sk-test", params=voice_session.session_params())
    cfg = m._build_session_config("hi", None)
    inp = cfg["audio"]["input"]
    assert inp["turn_detection"]["threshold"] == 0.7
    assert inp["turn_detection"]["create_response"] is True and inp["turn_detection"]["interrupt_response"] is True
    assert inp["transcription"] == {"model": "gpt-4o-transcribe", "language": "tr"}
    assert cfg["audio"]["output"]["voice"] == "shimmer"
    assert voice_session.session_config_is_valid(cfg)
    assert not voice_session.session_config_is_valid({"audio": {"input": {"turn_detection": None}}})
    # the module default is untouched
    from importlib import import_module
    default = import_module(cls.__module__).DEFAULT_SESSION_CONFIG
    assert "language" not in (default["audio"]["input"].get("transcription") or {})
    assert default["audio"]["input"]["turn_detection"]["threshold"] == 0.5
