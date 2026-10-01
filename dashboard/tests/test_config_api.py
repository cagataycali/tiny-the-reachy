"""Runtime settings routes: /api/config and /api/personas sit behind the same gate as every other /api route,
writes are validated against the schema and land in agent_log as persona "dashboard", resets go back to env.

Run: cd dashboard && REACHY_NO_AUTOAPP=1 python -m pytest tests -q
"""
import importlib
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("REACHY_NO_AUTOAPP", "1")
os.environ["REACHY_TOKEN"] = "test-token-do-not-use"
os.environ["REACHY_RP_ID"] = "reachy.test"
os.environ["REACHY_ASK_PREWARM"] = "0"
os.environ["REACHY_DASH_CAMERA_OFF"] = "1"
os.environ["VOICE_VAD_SILENCE_MS"] = "600"
os.environ["TELEGRAM_ALLOWED_USERS"] = "owner_fixture,424242"
os.environ["TELEGRAM_DEFAULT_CHAT_ID"] = "424242"
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from fastapi.testclient import TestClient  # noqa: E402

from dashboard import auth, config_api, robot as robot_mod, server  # noqa: E402

TOKEN = os.environ["REACHY_TOKEN"]
HDR = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db = tmp_path_factory.mktemp("mem") / "mem.db"
    config = importlib.import_module("tools.config")
    prompts = importlib.import_module("tools.prompts")
    config.DB = db
    prompts.DB = db
    robot_mod.MEM_DB = db
    auth.configure()
    app = server.create_app()
    yield TestClient(app, base_url="https://reachy.test")


def _agent_log(n=50):
    return robot_mod.agent_log_tail(n, 0)


@pytest.fixture(autouse=True)
def _no_rate_limit(client):
    """The real 5 writes/s limiter is a feature; these cells write faster than a human — drain it per test."""
    client.app.state.rate.clear()
    yield


@pytest.mark.parametrize("method,path", [("GET", "/api/config"), ("PUT", "/api/config"), ("DELETE", "/api/config/voice.lang"),
                                         ("GET", "/api/config/preview/telegram"), ("GET", "/api/personas"),
                                         ("POST", "/api/personas/tiny-voice/restart")])
def test_settings_routes_need_login(client, method, path):
    r = client.request(method, path, json={} if method in ("PUT", "POST") else None)
    assert r.status_code == 401, (method, path, r.text)
    assert r.json()["error"] == "login required"


def test_get_config_is_schema_driven_and_leaks_no_secret(client):
    r = client.get("/api/config", headers=HDR)
    assert r.status_code == 200, r.text
    d = r.json()
    keys = {k["key"] for k in d["schema"]}
    assert {"voice.provider", "voice.vad_silence_ms", "agent.model_id", "agent.tools.voice", "telegram.allowed_users",
            "telegram.heartbeat_photos", "agent.prompt_note.voice"} <= keys
    assert d["values"]["voice.vad_silence_ms"] == 600                 # env bootstrap
    assert d["values"]["telegram.allowed_users"] == ["owner_fixture", "424242"]
    assert d["overrides"] == {} or "voice.vad_silence_ms" not in d["overrides"]
    assert all(isinstance(v, bool) for v in d["secrets"].values())   # set/unset only
    assert "OPENAI_API_KEY" in d["secrets"]
    assert any(c["name"] == "shell" and c["dangerous"] for c in d["catalog"])
    assert set(d["defaults"]) == {"voice", "telegram", "thinker", "dashboard"}
    assert "memory" in d["defaults"]["voice"]
    text = r.text
    for forbidden in (TOKEN, "sk-", "BOT_TOKEN="):
        assert forbidden not in text


def test_put_validates_every_key_before_writing(client):
    r = client.put("/api/config", headers=HDR, json={"voice.vad_silence_ms": 650, "voice.vad_threshold": 7, "nope.key": 1})
    assert r.status_code == 422, r.text
    err = r.json()["detail"]["error"]
    assert "voice.vad_threshold" in err and "nope.key" in err
    assert client.get("/api/config", headers=HDR).json()["values"]["voice.vad_silence_ms"] == 600   # nothing written


def test_put_round_trip_logs_and_bumps_the_voice_generation(client):
    before = client.get("/api/config", headers=HDR).json()["generations"]["voice"]
    r = client.put("/api/config", headers=HDR, json={"voice.vad_silence_ms": "650", "telegram.heartbeat_photos": False})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["changed"]["voice.vad_silence_ms"] == {"old": "600", "new": "650"}
    assert d["restart"] == ["voice"]                                   # heartbeat_photos has no restart scope
    assert d["generations"]["voice"] == before + 1
    assert d["values"]["voice.vad_silence_ms"] == 650 and d["values"]["telegram.heartbeat_photos"] is False
    rows = [x for x in _agent_log() if x["persona"] == "dashboard" and "voice.vad_silence_ms" in x["text"]]
    assert rows and "600 -> 650" in rows[-1]["text"]
    # PUT the same value again: no change, no generation bump
    r2 = client.put("/api/config", headers=HDR, json={"voice.vad_silence_ms": 650})
    assert r2.json()["changed"] == {} and r2.json()["generations"]["voice"] == before + 1


def test_delete_resets_to_env(client):
    r = client.delete("/api/config/voice.vad_silence_ms", headers=HDR)
    assert r.status_code == 200 and r.json()["removed"] is True
    assert r.json()["value"] == 600
    assert client.delete("/api/config/does.not.exist", headers=HDR).status_code == 422


def test_prompt_note_round_trips_through_prompts_py_and_shows_in_preview(client):
    r = client.put("/api/config", headers=HDR, json={"agent.prompt_note.telegram": "Answer in Turkish when spoken to in Turkish."})
    assert r.status_code == 200, r.text
    prompts = importlib.import_module("tools.prompts")
    assert prompts.get_override("telegram") == "Answer in Turkish when spoken to in Turkish."
    p = client.get("/api/config/preview/telegram", headers=HDR)
    assert p.status_code == 200, p.text
    d = p.json()
    assert "Personality note" in d["prompt"] and "Answer in Turkish" in d["prompt"]
    assert "telegram" in d["tools"] and d["chars"] == len(d["prompt"])
    assert client.get("/api/config/preview/nobody", headers=HDR).status_code == 422
    # clearing the note removes the override
    client.app.state.rate.clear()
    client.put("/api/config", headers=HDR, json={"agent.prompt_note.telegram": ""})
    assert prompts.get_override("telegram") is None


def test_tools_list_narrows_the_persona_and_unknown_names_are_dropped(client):
    r = client.put("/api/config", headers=HDR, json={"agent.tools.telegram": ["memory", "telegram", "not_a_tool"]})
    assert r.status_code == 200, r.text
    d = client.get("/api/config", headers=HDR).json()
    assert d["effective_tools"]["telegram"] == ["memory", "telegram"]
    assert d["values"]["agent.tools.telegram"] == ["memory", "telegram", "not_a_tool"]   # stored as typed, applied filtered
    p = client.get("/api/config/preview/telegram", headers=HDR).json()
    assert p["tools"] == ["memory", "telegram"]
    client.app.state.rate.clear()
    client.delete("/api/config/agent.tools.telegram", headers=HDR)
    assert "shell" in client.get("/api/config", headers=HDR).json()["effective_tools"]["telegram"]


def test_personas_status_and_restart_are_allow_listed_and_cooled_down(client, monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)

        class R:
            stdout = "ActiveState=active\nSubState=running\nMainPID=4242\nActiveEnterTimestamp=Wed 2026-10-01 12:00:00 UTC\nNRestarts=0\n"
            stderr = ""
            returncode = 0
        return R()

    monkeypatch.setattr(config_api.subprocess, "run", fake_run)
    monkeypatch.setattr(config_api, "_last_restart", {})
    r = client.get("/api/personas", headers=HDR)
    assert r.status_code == 200
    units = {u["unit"]: u for u in r.json()["units"]}
    assert set(units) == {"tiny-voice", "tiny-telegram", "tiny-thinker"}
    assert units["tiny-voice"]["active"] == "active" and units["tiny-voice"]["pid"] == 4242

    drain = client.app.state.rate.clear
    assert client.post("/api/personas/reachy-dashboard/restart", headers=HDR).status_code == 422   # not allow-listed
    drain(); assert client.post("/api/personas/tiny-mhs/restart", headers=HDR).status_code == 422
    drain(); r = client.post("/api/personas/tiny-thinker/restart", headers=HDR)
    assert r.status_code == 200, r.text
    assert ["systemctl", "--user", "restart", "tiny-thinker"] in calls
    drain(); r = client.post("/api/personas/tiny-thinker/restart", headers=HDR)
    assert r.status_code == 429 and "restarted" in r.json()["detail"]["error"]                    # cooldown, not the limiter
    assert any("restarted tiny-thinker" in x["text"] for x in _agent_log() if x["persona"] == "dashboard")


def test_cross_origin_write_is_refused(client):
    r = client.put("/api/config", headers={**HDR, "Origin": "https://evil.example"}, json={"voice.lang": "tr"})
    assert r.status_code == 403
