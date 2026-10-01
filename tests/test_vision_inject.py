"""take_photo sends the frame (ImageBlock, no response requested) then the question
(TextBlock, one response) through agent.send on Strands 1.57+; the session tuning
pins language / VAD from env via the model's native `params` and never mutates
Strands' module-level default config."""
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


def test_inject_is_image_then_question_through_agent_send():
    agent = _Agent()
    asyncio.run(vision._inject(agent, b"AAA", "what do you see?"))
    assert [type(c).__name__ for c in agent.sent] == ["ImageBlock", "TextBlock"]
    img, text = agent.sent
    assert img.format == "jpeg" and img.source == {"bytes": b"AAA"}
    assert text.text == "what do you see?"


def test_openai_image_send_creates_no_response_of_its_own():
    """1.57.1 OpenAIRealtimeModel: the image item is created silently, the text item asks for
    the (single) response - so image-then-text is one answer that sees both."""
    cls = vision._realtime_model_class()
    if cls is None:
        pytest.skip("no Realtime model class in this env")
    import inspect
    assert hasattr(cls, "_send_image_content")
    assert "response" not in inspect.getsource(cls._send_image_content).replace("_send_event", "")
    assert "_request_response" in inspect.getsource(cls._send_text_content)
    assert not hasattr(vision, "_patch_openai_image_support"), "the 1.20 monkey patch must be gone"


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
