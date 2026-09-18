"""take_photo puts ONE (question + image) message in front of the realtime model and
asks for ONE response; the session tuning pins language / VAD from env and never
mutates Strands' module-level default config."""
import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import vision  # noqa: E402
from tools import voice_session  # noqa: E402


class _Model:
    def __init__(self):
        self._connection_id = "conn"
        self.events = []

    async def _send_event(self, ev):
        self.events.append(ev)


class _Agent:
    def __init__(self, model):
        self.model = model
        self.sent = []

    async def send(self, content):
        self.sent.append(content)


def test_inject_is_one_item_and_one_response():
    model = _Model()
    agent = _Agent(model)
    asyncio.run(vision._inject(agent, "QUFB", "what do you see?"))
    assert [e["type"] for e in model.events] == ["conversation.item.create", "response.create"]
    content = model.events[0]["item"]["content"]
    assert content[0] == {"type": "input_text", "text": "what do you see?"}
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/jpeg;base64,QUFB")
    assert agent.sent == [], "wire path must not also go through agent.send (double response)"


def test_inject_falls_back_to_agent_send_for_other_providers():
    class _Other:
        pass
    agent = _Agent(_Other())
    asyncio.run(vision._inject(agent, "QUFB", "q"))
    assert [type(c).__name__ for c in agent.sent] == ["BidiImageInputEvent", "BidiTextInputEvent"]


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
    assert out["audio"]["input"]["turn_detection"]["threshold"] == 0.6


def test_bad_env_values_fall_back(monkeypatch):
    monkeypatch.setenv("VOICE_VAD_THRESHOLD", "loud")
    monkeypatch.setenv("VOICE_VAD_SILENCE_MS", "x")
    o = voice_session.session_overrides()["turn_detection"]
    assert o["threshold"] == 0.6 and o["silence_duration_ms"] == 600


def test_session_patch_is_idempotent_and_applies():
    cls = vision._realtime_model_class()
    if cls is None:
        pytest.skip("no Realtime model class in this env")
    assert voice_session.patch_openai_realtime_session()
    assert voice_session.patch_openai_realtime_session()
    m = cls.__new__(cls)
    m.config = {"audio": {}, "inference": {}}
    cfg = m._build_session_config("hi", None)
    assert cfg["audio"]["input"]["turn_detection"]["threshold"] == voice_session.session_overrides()["turn_detection"]["threshold"]
