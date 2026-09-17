"""dashboard/tracking.Tracker against a FAKE daemon (reachy-mini 1.10 REST shape) — no robot needed.

Run: cd dashboard && REACHY_NO_AUTOAPP=1 python -m pytest tests -q
"""
import os
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("REACHY_NO_AUTOAPP", "1")
os.environ["REACHY_DASH_CAMERA_OFF"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dashboard import tracking  # noqa: E402


class FakeDaemon:
    """Mimics /api/media/tracking/{enable,disable,face} of reachy-mini 1.10.0."""

    def __init__(self, camera=True):
        self.camera = camera
        self.enabled = False
        self.weight = None
        self.face = {"detected": False, "x": None, "y": None, "roll": None, "ts": None}
        self.calls = []
        self.down = False

    def __call__(self, method, path, body=None, timeout=4.0):
        self.calls.append((method, path, body))
        if self.down:
            raise RuntimeError("daemon unreachable")
        if path == "/api/media/tracking/enable":
            if not self.camera:
                return {"status": "unavailable", "enabled": False}
            self.enabled, self.weight = True, float((body or {}).get("weight", 1.0))
            return {"status": "ok", "enabled": True}
        if path == "/api/media/tracking/disable":
            self.enabled, self.weight = False, None
            return {"status": "ok", "enabled": False}
        if path == "/api/media/tracking/face":
            return {"status": "ok", "face_target": dict(self.face)}
        raise AssertionError(path)

    def enables(self):
        return [b["weight"] for m, p, b in self.calls if p.endswith("/enable")]


@pytest.fixture
def fd(monkeypatch):
    monkeypatch.setattr(tracking, "FACE_POLL_HZ", 50.0)   # fast poll for the tests
    return FakeDaemon()


def mk(fd, events=None):
    t = tracking.Tracker(fd, on_change=(events.append if events is not None else None))
    yield_ = t
    return yield_


def test_toggle_is_idempotent_and_hits_daemon_once(fd):
    t = mk(fd)
    st = t.set_enabled(True)
    assert st["enabled"] is True and st["weight"] == 1.0 and st["engine"] == "daemon-yunet"
    t.set_enabled(True)
    assert fd.enables() == [1.0]                       # second ON is a no-op
    t.set_enabled(False)
    t.set_enabled(False)
    assert [p for _, p, _ in fd.calls if p.endswith("/disable")] == ["/api/media/tracking/disable"]
    assert fd.enabled is False and t.status()["enabled"] is False
    t.stop()


def test_status_shape(fd):
    t = mk(fd)
    st = t.status()
    for k in ("enabled", "paused", "holds", "detected", "x", "y", "roll", "weight", "available", "error",
              "face_age_s", "engine", "poll_hz"):
        assert k in st, k
    assert st["enabled"] is False and st["detected"] is False and st["holds"] == []


def test_face_poll_updates_status(fd):
    t = mk(fd)
    t.set_enabled(True)
    fd.face = {"detected": True, "x": 0.25, "y": -0.1, "roll": 0.02, "ts": 123.0}
    deadline = time.time() + 2
    while time.time() < deadline and not t.status()["detected"]:
        time.sleep(0.02)
    st = t.status()
    assert st["detected"] is True and st["x"] == 0.25 and st["y"] == -0.1
    t.stop()


def test_speaking_hold_only_once_a_face_is_locked(fd):
    """Pollen: pause only when a face is locked, otherwise speech would block acquisition."""
    t = mk(fd)
    t.set_enabled(True)
    st = t.hold("speaking", ttl=5)
    assert st["paused"] is False and fd.weight == 1.0   # no face → keep looking for one
    fd.face = {"detected": True, "x": 0.0, "y": 0.0, "roll": 0.0, "ts": 1.0}
    deadline = time.time() + 2
    while time.time() < deadline and not t.status()["detected"]:
        time.sleep(0.02)
    st = t.hold("speaking", ttl=5)
    assert st["paused"] is True and fd.weight == 0.0    # face locked → weight 0 while speaking
    st = t.release("speaking")
    assert st["paused"] is False and fd.weight == 1.0   # hand the head back
    assert fd.enables()[-2:] == [0.0, 1.0]
    t.stop()


def test_emotion_and_look_holds_pause_and_resume(fd):
    t = mk(fd)
    t.set_enabled(True)
    t.hold("emotion:cheerful1", ttl=5)
    assert fd.weight == 0.0
    t.hold("look", ttl=5)
    t.release("emotion:cheerful1")
    assert fd.weight == 0.0 and t.status()["holds"] == ["look"]   # still one live hold
    t.release("look")
    assert fd.weight == 1.0 and t.status()["holds"] == []
    t.stop()


def test_hold_expires_by_itself(fd):
    t = mk(fd)
    t.set_enabled(True)
    t.hold("emotion:dance1", ttl=0.5)                    # min ttl is 0.5 s
    assert fd.weight == 0.0
    deadline = time.time() + 2
    while time.time() < deadline and fd.weight != 1.0:
        time.sleep(0.05)
    assert fd.weight == 1.0                              # the poll loop re-applied after expiry
    t.stop()


def test_holds_while_disabled_do_not_touch_the_daemon(fd):
    t = mk(fd)
    t.hold("speaking", ttl=5)
    t.release("speaking")
    assert fd.calls == []


def test_no_camera_reports_unavailable_and_stays_off(monkeypatch):
    monkeypatch.setattr(tracking, "FACE_POLL_HZ", 50.0)
    fd = FakeDaemon(camera=False)
    t = mk(fd)
    with pytest.raises(RuntimeError):
        t.set_enabled(True)
    st = t.status()
    assert st["enabled"] is False and st["available"] is False and "camera" in (st["error"] or "")


def test_daemon_down_error_is_returned_not_swallowed(fd):
    t = mk(fd)
    fd.down = True
    with pytest.raises(RuntimeError):
        t.set_enabled(True)
    assert t.status()["enabled"] is False


def test_stop_disables_tracking_on_shutdown(fd):
    t = mk(fd)
    t.set_enabled(True)
    t.stop()
    assert fd.enabled is False


def test_events_emitted_on_change(fd):
    evs = []
    t = mk(fd, evs)
    t.set_enabled(True)
    assert evs and evs[-1]["type"] == "tracking" and evs[-1]["enabled"] is True
    n = len(evs)
    t.hold("look", 5)
    assert len(evs) == n + 1 and evs[-1]["paused"] is True
    t.stop()


def test_adopt_mirrors_a_daemon_that_is_already_tracking(fd):
    fd.enabled, fd.weight = True, 1.0
    fd.face = {"detected": True, "x": 0.1, "y": 0.0, "roll": 0.0, "ts": 55.0}   # ts set ⇔ daemon detector running
    t = mk(fd)
    assert t.adopt() is True
    st = t.status()
    assert st["enabled"] is True and st["detected"] is True and fd.weight == 1.0
    t.stop()
    assert fd.enabled is False


def test_adopt_leaves_an_idle_daemon_alone(fd):
    t = mk(fd)
    assert t.adopt() is False
    assert t.status()["enabled"] is False and fd.enables() == []
