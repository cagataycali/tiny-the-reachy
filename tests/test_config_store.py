"""tools/config.py — the one runtime config store (DB -> env -> default) every persona reads at build time,
and the places that must read it live: telegram allow-list / default chat, tiny's tool lists, the voice watcher."""
import asyncio
import importlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

config = importlib.import_module("tools.config")
prompts = importlib.import_module("tools.prompts")


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "mem.db"
    monkeypatch.setattr(config, "DB", path)
    monkeypatch.setattr(prompts, "DB", path)
    return path


def test_resolution_order_db_env_default(db, monkeypatch):
    monkeypatch.delenv("VOICE_VAD_SILENCE_MS", raising=False)
    assert config.get("voice.vad_silence_ms") == 600                      # code default
    monkeypatch.setenv("VOICE_VAD_SILENCE_MS", "700")
    assert config.get("voice.vad_silence_ms") == 700                      # env
    config.set_many({"voice.vad_silence_ms": 650}, by="test")
    assert config.get("voice.vad_silence_ms") == 650                      # DB wins
    assert config.reset("voice.vad_silence_ms", by="test") is True
    assert config.get("voice.vad_silence_ms") == 700                      # back to env
    assert config.reset("voice.vad_silence_ms", by="test") is False


def test_env_aliases_and_bad_env_fall_back(db, monkeypatch):
    monkeypatch.setenv("VOICE_PROVIDER", "nova")
    assert config.get("voice.provider") == "nova_sonic"
    monkeypatch.setenv("VOICE_PROVIDER", "unknownbox")
    assert config.get("voice.provider") == "openai"                       # invalid env → code default, never a crash
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", " alice ,, 42 ")
    assert config.get("telegram.allowed_users") == ["alice", "42"]
    monkeypatch.setenv("TINY_MCP", "1")
    assert config.get("agent.fleet_tools") is True


@pytest.mark.parametrize("key,raw,msg", [
    ("voice.vad_threshold", 1.5, "at most 1"),
    ("voice.vad_threshold", "abc", "number"),
    ("voice.vad_silence_ms", 50, "at least 100"),
    ("voice.vad_silence_ms", 600.5, "whole number"),
    ("voice.provider", "siri", "one of openai, nova_sonic, gemini"),
    ("voice.turn_detection", "magic", "one of server_vad, semantic_vad"),
    ("telegram.heartbeat_photos", "maybe", "true or false"),
    ("voice.model", "two\nlines", "one line"),
    ("agent.tools.voice", 42, "list"),
    ("not.a.key", 1, "unknown key"),
])
def test_validation_messages(db, key, raw, msg):
    with pytest.raises(ValueError) as e:
        config.set_many({key: raw})
    assert msg in str(e.value) and key in str(e.value)


def test_set_many_is_all_or_nothing(db):
    with pytest.raises(ValueError):
        config.set_many({"voice.lang": "tr", "voice.vad_threshold": 9})
    assert "voice.lang" not in config.overrides()


def test_generation_bumps_only_for_scoped_keys_that_changed(db):
    assert config.generations() == {"voice": 0, "agent": 0}
    r = config.set_many({"telegram.heartbeat_photos": False})            # restart scope none
    assert r["restart"] == [] and config.generations() == {"voice": 0, "agent": 0}
    r = config.set_many({"voice.lang": "tr", "agent.model_id": "global.anthropic.claude-sonnet-4-5"})
    assert r["restart"] == ["agent", "voice"] and config.generations() == {"voice": 1, "agent": 1}
    r = config.set_many({"voice.lang": "tr"})                             # same value: no bump
    assert r["changed"] == {} and config.generation("voice") == 1
    config.reset("voice.lang")                                            # a reset that changes the value bumps too
    assert config.generation("voice") == 2


def test_history_records_old_and_new(db):
    config.set_many({"voice.name": "shimmer"}, by="dashboard")
    config.set_many({"voice.name": "coral"}, by="dashboard")
    h = config.history("voice.name")
    assert [(x["old"], x["new"], x["source"]) for x in h] == [("shimmer", "coral", "dashboard"), ("", "shimmer", "dashboard")]


def test_prompt_notes_are_prompts_py_rows(db):
    config.set_many({"agent.prompt_note.voice": "be brief"}, by="dashboard")
    assert prompts.get_override("voice") == "be brief"
    assert config.overrides()["agent.prompt_note.voice"] == "be brief"
    assert config.generation("voice") == 1                                # the voice prompt is built at session start
    prompts.set_override("voice", "FULL: replace me", source="tool")      # the tool side stays one source
    assert config.get("agent.prompt_note.voice") == "FULL: replace me"
    config.set_many({"agent.prompt_note.voice": ""})
    assert prompts.get_override("voice") is None


def test_allowed_users_strip_the_at_sign_and_tools_list_empty_means_default(db):
    config.set_many({"telegram.allowed_users": "@alice\n@bob, 42", "agent.tools.voice": []})
    assert config.get("telegram.allowed_users") == ["alice", "bob", "42"]
    assert config.get("agent.tools.voice") is None
    assert config.tools_for("voice", ["memory"]) is None


def test_tools_for_drops_unknown_names_with_a_warning(db, capsys):
    config.set_many({"agent.tools.thinker": ["memory", "ghost"]})
    assert config.tools_for("thinker", ["memory", "shell"]) == ["memory"]
    assert "ghost" in capsys.readouterr().err


def test_schema_never_names_a_secret():
    names = " ".join(k["key"] + k["help"] + k["label"] for k in config.schema()).lower()
    for bad in ("api_key", "token", "secret", "password", "reachy_"):
        assert bad not in names, bad
    assert all(k["restart"] in config.SCOPES for k in config.schema())


# ── the readers that must not cache ───────────────────────────────────────────
def test_telegram_allow_list_and_default_chat_read_live(db, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "alice")
    monkeypatch.setenv("TELEGRAM_DEFAULT_CHAT_ID", "111")
    tg = importlib.import_module("tools.telegram")
    assert tg._user_allowed({"username": "alice"}) and not tg._user_allowed({"username": "mallory", "id": 7})
    assert tg.default_chat_id() == "111"
    config.set_many({"telegram.allowed_users": ["mallory"], "telegram.default_chat_id": "222"})
    assert tg._user_allowed({"username": "mallory"}) and not tg._user_allowed({"username": "alice"})
    assert tg._user_allowed({"id": 9, "username": ""}) is False
    assert tg.default_chat_id() == "222"
    config.set_many({"telegram.allowed_users": []})
    assert tg._user_allowed({"username": "anyone"})                       # empty = everyone (as before)


def test_tiny_builds_tool_lists_and_prompts_from_config(db, monkeypatch):
    monkeypatch.setenv("TELEGRAM_DEFAULT_CHAT_ID", "")
    tiny = importlib.import_module("tiny")
    monkeypatch.setattr(tiny.tiny_mcp, "get_tools", lambda *a, **k: [])
    catalog = {c["name"] for c in tiny.tool_catalog()}
    assert {"memory", "shell", "telegram", "reachy_look", "dispatch"} <= catalog
    assert {c["name"] for c in tiny.tool_catalog() if c["dangerous"]} >= {"shell", "dispatch", "manage_tools"}
    assert tiny.effective_tool_names("voice") == tiny.default_tool_names("voice")
    config.set_many({"agent.tools.voice": ["memory", "reachy_look", "ghost"], "agent.model_id": "global.anthropic.claude-sonnet-4-5",
                     "telegram.default_chat_id": "4242", "telegram.allowed_users": ["owner_fixture"], "telegram.heartbeat_photos": False})
    assert [tiny._tool_name(t) for t in tiny.build_voice_tools(persona="voice")] == ["memory", "reachy_look"]
    assert tiny.effective_tool_names("telegram") == tiny.default_tool_names("telegram")   # other personas untouched
    assert tiny.model_id() == "global.anthropic.claude-sonnet-4-5" and tiny.MODEL_ID != tiny.model_id()
    voice_prompt = tiny._voice_prompt()
    assert "@owner_fixture" in voice_prompt and "`4242`" in voice_prompt
    thinker_prompt = tiny._thinker_prompt()
    assert "NO TELEGRAM THIS CYCLE" in thinker_prompt and "TELEGRAM A PHOTO" not in thinker_prompt
    config.set_many({"telegram.heartbeat_photos": True})
    assert "TELEGRAM A PHOTO + STATUS" in tiny._thinker_prompt() and "chat_id='4242'" in tiny._thinker_prompt()
    assert tiny.voice_settings()["provider"] == "openai"


def test_voice_session_overrides_follow_config(db):
    vs = importlib.import_module("tools.voice_session")
    config.set_many({"voice.turn_detection": "semantic_vad", "voice.vad_eagerness": "high", "voice.lang": "tr",
                     "voice.transcribe_prompt": "Turkish or English"})
    o = vs.session_overrides()
    assert o["turn_detection"] == {"type": "semantic_vad", "eagerness": "high", "interrupt_response": True, "create_response": True}
    assert o["transcription"] == {"model": "gpt-4o-transcribe", "language": "tr", "prompt": "Turkish or English"}
    config.set_many({"voice.turn_detection": "server_vad", "voice.vad_threshold": 0.7, "voice.vad_silence_ms": 900})
    t = vs.session_overrides()["turn_detection"]
    assert t["type"] == "server_vad" and t["threshold"] == 0.7 and t["silence_duration_ms"] == 900


# ── the voice watcher ends the live session the way stop_conversation does: agent.cancel() ──
class _FakeAgent:
    """Stands in for a strands.bidi BidiAgent: cancel() flips a signal run() is waiting on."""
    def __init__(self):
        self.cancelled, self.ev = 0, asyncio.Event()

    def cancel(self):
        self.cancelled += 1
        self.ev.set()

    async def run(self):
        await self.ev.wait()                             # the event loop honours cancel_signal → run returns


def test_watch_config_ends_the_session_on_a_generation_change(db, capsys):
    vl = importlib.import_module("voice_listener")
    gen = {"n": 3}

    async def go():
        agent = _FakeAgent()
        task = asyncio.ensure_future(agent.run())

        async def bump():
            await asyncio.sleep(0.1)
            gen["n"] = 4
        asyncio.ensure_future(bump())
        return await vl.watch_config(agent, task, generation_fn=lambda: gen["n"], poll_s=0.03), agent, task

    restarted, agent, task = asyncio.run(go())
    assert restarted is True and task.done() and not task.cancelled()
    assert agent.cancelled == 1                           # ended via BidiAgent.cancel(), not a task cancel
    assert "config generation 3 -> 4" in capsys.readouterr().err


def test_watch_config_returns_false_when_the_session_ends_by_itself(db):
    vl = importlib.import_module("voice_listener")

    async def go():
        async def run():
            await asyncio.sleep(0.05)
        task = asyncio.ensure_future(run())
        return await vl.watch_config(_FakeAgent(), task, generation_fn=lambda: 1, poll_s=0.02)
    assert asyncio.run(go()) is False


def test_watch_config_cancels_the_task_when_the_agent_has_no_cancel(db):
    vl = importlib.import_module("voice_listener")

    class Bare:
        async def run(self):
            await asyncio.sleep(30)
    gen = {"n": 0}

    async def go():
        task = asyncio.ensure_future(Bare().run())

        async def bump():
            await asyncio.sleep(0.05)
            gen["n"] = 1
        asyncio.ensure_future(bump())
        r = await vl.watch_config(Bare(), task, generation_fn=lambda: gen["n"], poll_s=0.02)
        return r, task.cancelled()
    assert asyncio.run(go()) == (True, True)


def test_bidi_model_builder_reads_the_configured_model(db, monkeypatch):
    """Regression: `_build_bidi_model` names its provider_config `cfg`, which shadowed the config reader on the robot
    ('dict' object is not callable, crash loop at deploy 2026-10-01)."""
    tiny = importlib.import_module("tiny")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.delenv("VOICE_MODEL", raising=False)
    config.set_many({"voice.model": "gpt-realtime-test", "voice.name": "coral"})
    model = tiny._build_bidi_model("openai", "coral")
    assert getattr(model, "model_id", None) == "gpt-realtime-test"
