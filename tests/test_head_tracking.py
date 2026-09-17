"""tools/head_tracking — the personas' toggle + the voice SpeakingHandoff, against a fake dashboard."""
import asyncio
import os
import sys
import urllib.error

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import importlib  # noqa: E402
ht = importlib.import_module("tools.head_tracking")  # `from tools import head_tracking` would give the TOOL (package re-exports it)


class FakeDash:
    def __init__(self):
        self.enabled = False
        self.holds = {}
        self.calls = []
        self.down = False

    def __call__(self, method, path="/api/tracking", body=None, timeout=6.0):
        self.calls.append((method, path, body))
        if self.down:
            raise urllib.error.URLError("connection refused")
        if path == "/api/tracking" and method == "POST":
            self.enabled = bool(body["enabled"])
            return {"ok": True, "tracking": self.status()}
        if path == "/api/tracking":
            return self.status()
        if path == "/api/tracking/hold":
            if body["on"]:
                self.holds[body["name"]] = body["ttl"]
            else:
                self.holds.pop(body["name"], None)
            return {"ok": True, "tracking": self.status()}
        raise AssertionError(path)

    def status(self):
        return {"enabled": self.enabled, "paused": bool(self.holds) and self.enabled, "holds": sorted(self.holds),
                "detected": False, "x": None, "y": None, "available": True, "error": None, "face_age_s": None,
                "engine": "daemon-yunet"}


@pytest.fixture
def dash(monkeypatch):
    d = FakeDash()
    monkeypatch.setattr(ht, "_call", d)
    return d


def _text(r):
    return r["content"][0]["text"]


def test_toggle_on_off(dash):
    r = ht.head_tracking(True)
    assert r["status"] == "success" and dash.enabled is True and "following" in _text(r)
    r = ht.head_tracking(False)
    assert r["status"] == "success" and dash.enabled is False and "stopped following" in _text(r)


def test_status_text(dash):
    dash.enabled = True
    dash.holds = {"speaking": 30}
    r = ht.head_tracking_status()
    assert r["status"] == "success"
    assert "ON" in _text(r) and "paused while speaking" in _text(r)
    assert r["content"][1]["json"]["enabled"] is True


def test_errors_are_returned_not_raised(dash):
    dash.down = True
    r = ht.head_tracking(True)
    assert r["status"] == "error" and "unreachable" in _text(r)
    assert ht.head_tracking_status()["status"] == "error"
    assert ht.tracking_hold("look", True) is False       # best effort, never raises
    ht.stop_head_tracking()                             # no exception


def test_stop_head_tracking_only_when_on(dash):
    ht.stop_head_tracking()
    assert all(m == "GET" for m, _, _ in dash.calls)    # nothing to turn off → no POST
    dash.enabled = True
    ht.stop_head_tracking()
    assert dash.enabled is False


def test_speaking_handoff_weights(dash):
    dash.enabled = True
    h = ht.SpeakingHandoff(tail_s=0.05)

    async def run():
        await h({"type": "bidi_response_start"})
        assert dash.holds == {}
        await h({"type": "bidi_audio_stream", "audio": b"..."})
        await h({"type": "bidi_audio_stream", "audio": b"..."})
        assert dash.holds == {"speaking": 30.0}         # ONE hold for the whole utterance
        assert sum(1 for _, p, _ in dash.calls if p.endswith("/hold")) == 1
        await h({"type": "bidi_response_complete"})
        assert "speaking" in dash.holds                 # tail: playback still draining
        await asyncio.sleep(0.15)
        assert dash.holds == {}                         # released → weight 1 on the daemon
        # interruption releases immediately
        await h({"type": "bidi_audio_stream"})
        assert "speaking" in dash.holds
        await h({"type": "bidi_interruption", "reason": "user_speech"})
        assert dash.holds == {}
        # stop() is safe and idempotent
        await h.stop()
    asyncio.run(run())


def test_handoff_survives_dashboard_down(dash):
    dash.down = True
    h = ht.SpeakingHandoff(tail_s=0)

    async def run():
        await h({"type": "bidi_audio_stream"})
        await h({"type": "bidi_response_complete"})
    asyncio.run(run())                                  # no exception


def test_tools_registered_everywhere():
    from tools import TINY_SENSING_TOOLS, TINY_ALL_TOOLS
    names = {getattr(t, "tool_name", getattr(t, "__name__", "")) for t in TINY_ALL_TOOLS}
    assert {"head_tracking", "head_tracking_status"} <= names
    assert ht.head_tracking in TINY_SENSING_TOOLS
