"""tools/turn_to_sound.py — thin toggle over the dashboard's /api/doa."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import importlib  # noqa: E402

t2s = importlib.import_module("tools.turn_to_sound")   # `from tools import turn_to_sound` gives the TOOL (package re-export)


def _resp(payload):
    m = mock.MagicMock()
    m.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    return m


def test_turn_to_sound_posts_enabled():
    with mock.patch("tools.head_tracking.urllib.request.urlopen") as uo:
        uo.return_value = _resp({"enabled": True, "turns": 2, "angle_deg": 30.0, "delta_deg": 60.0, "speech": True, "why": None})
        r = t2s.turn_to_sound(True)
    assert r["status"] == "success"
    req = uo.call_args[0][0]
    assert req.full_url.endswith("/api/doa") and req.get_method() == "POST"
    assert json.loads(req.data) == {"enabled": True}
    text = r["content"][0]["text"]
    assert "turn-to-sound ON" in text and "60° to the left" in text


def test_turn_to_sound_off_and_status():
    with mock.patch("tools.head_tracking.urllib.request.urlopen") as uo:
        uo.return_value = _resp({"enabled": False, "turns": 0, "angle_deg": None, "why": "disabled"})
        r = t2s.turn_to_sound(False)
        assert "turn-to-sound OFF" in r["content"][0]["text"]
        uo.return_value = _resp({"enabled": True, "turns": 1, "angle_deg": 120.0, "delta_deg": -30.0, "speech": False, "why": "rate limit"})
        r = t2s.turn_to_sound_status()
        assert uo.call_args[0][0].get_method() == "GET"
        assert "30° to the right" in r["content"][0]["text"] and "waiting: rate limit" in r["content"][0]["text"]


def test_turn_to_sound_dashboard_down():
    with mock.patch("tools.head_tracking.urllib.request.urlopen", side_effect=OSError("refused")):
        r = t2s.turn_to_sound(True)
    assert r["status"] == "error" and "unreachable" in r["content"][0]["text"]
