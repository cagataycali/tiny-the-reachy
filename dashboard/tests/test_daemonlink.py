"""daemonlink — the dashboard must not hurt the daemon (EMFILE incident 2026-09-17).

A tiny real HTTP server stands in for the daemon so we can count TCP connections and requests for real.
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("REACHY_NO_AUTOAPP", "1")

from dashboard import daemonlink  # noqa: E402
from dashboard.tracking import Tracker  # noqa: E402


class FakeDaemon(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), Handler)
        self.requests: list = []
        self.connections = 0
        self.running: list = []
        self.face_ts = None
        self.lock = threading.Lock()

    def process_request(self, request, client_address):
        with self.lock:
            self.connections += 1
        super().process_request(request, client_address)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"          # keep-alive capable, like uvicorn

    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        srv: FakeDaemon = self.server  # type: ignore[assignment]
        with srv.lock:
            srv.requests.append(("GET", self.path))
        if self.path.startswith("/api/state/full"):
            self._send({"head_pose": {"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0.1}, "body_yaw": 0.0,
                        "antennas_position": [0, 0], "head_joints": [0] * 7, "target_head_joints": [0] * 7,
                        "doa": {"angle": 1.2, "speech_detected": True}, "timestamp": time.time()})
        elif self.path.startswith("/api/move/running"):
            self._send(srv.running)
        elif self.path.startswith("/api/media/tracking/face"):
            self._send({"face_target": {"detected": False, "x": None, "y": None, "roll": None, "ts": srv.face_ts}})
        else:
            self._send({"detail": "nope"}, 404)

    def do_POST(self):
        srv: FakeDaemon = self.server  # type: ignore[assignment]
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        with srv.lock:
            srv.requests.append(("POST", self.path, body))
        if self.path == "/api/media/tracking/enable":
            srv.face_ts = time.time()
            self._send({"enabled": True})
        elif self.path == "/api/media/tracking/disable":
            srv.face_ts = None
            self._send({"enabled": False})
        else:
            self._send({"ok": True})


@pytest.fixture
def fake():
    srv = FakeDaemon()
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()


def _session(fake) -> daemonlink.Session:
    return daemonlink.Session(f"http://127.0.0.1:{fake.server_address[1]}")


def test_session_reuses_one_connection(fake):
    s = _session(fake)
    for _ in range(25):
        assert s.request("GET", "/api/move/running") == []
    assert len(fake.requests) == 25
    assert fake.connections <= 2, f"{fake.connections} TCP connections for 25 requests — keep-alive is broken"


def test_session_errors_match_old_contract(fake):
    s = _session(fake)
    with pytest.raises(RuntimeError, match="→ 404"):
        s.request("GET", "/api/nothing")
    dead = daemonlink.Session("http://127.0.0.1:1")
    with pytest.raises(RuntimeError, match="unreachable"):
        dead.request("GET", "/api/x", timeout=0.5)
    assert dead.errors == 1


def test_stream_fallback_is_rate_limited(fake, monkeypatch):
    monkeypatch.setattr(daemonlink, "FALLBACK_HZ", 4.0)
    st = daemonlink.StateStream(_session(fake))      # never started → no WS → REST fallback path
    frames = [st.latest()[0] for _ in range(40)]     # 40 reads as fast as the WS pump would
    assert all(f and "head_pose" in f for f in frames)
    gets = [r for r in fake.requests if r[1].startswith("/api/state/full")]
    assert 1 <= len(gets) <= 2, f"{len(gets)} REST polls for 40 reads — fallback must be ≤ FALLBACK_HZ"
    assert "with_target_head_pose" not in gets[0][1]  # daemon asserts on it before the first goto
    assert "with_doa=true" in gets[0][1]


def test_stream_url_asks_for_doa_and_targets():
    st = daemonlink.StateStream(daemonlink.Session("http://127.0.0.1:8000"))
    assert st.url.startswith("ws://127.0.0.1:8000/api/state/ws/full?")
    assert "with_doa=true" in st.url and "with_target_head_joints=true" in st.url
    assert "with_target_head_pose" not in st.url


def test_moves_probe_idle_vs_armed(fake, monkeypatch):
    monkeypatch.setattr(daemonlink, "MOVES_IDLE_S", 3.0)
    monkeypatch.setattr(daemonlink, "MOVES_ACTIVE_HZ", 20.0)
    mp = daemonlink.MovesProbe(_session(fake))
    for _ in range(30):
        mp.running()
    idle = len([r for r in fake.requests if r[1] == "/api/move/running"])
    assert idle == 1, f"idle probe should be ~1 per {daemonlink.MOVES_IDLE_S}s, got {idle}"
    mp.arm(5.0)
    for _ in range(5):
        mp.running()
        time.sleep(0.06)
    armed = len([r for r in fake.requests if r[1] == "/api/move/running"]) - idle
    assert armed >= 4, f"armed probe should follow MOVES_ACTIVE_HZ, got {armed} in 0.3 s"


def test_pressure_shape_and_warn(monkeypatch):
    monkeypatch.setattr(daemonlink, "_daemon_pid", lambda: os.getpid())
    monkeypatch.setattr(daemonlink, "_sock_count", lambda state, port=8000: 7 if state == "close-wait" else 3)
    p = daemonlink.pressure(force=True)
    assert p["pid"] == os.getpid()
    if os.path.isdir("/proc"):                        # Linux (the CM4): real fd count + limit
        assert isinstance(p["fds"], int) and p["fds"] > 0 and p["fd_limit"]
    assert p["close_wait"] == 7 and p["established"] == 3
    assert p["warn"] is None
    monkeypatch.setattr(daemonlink, "CLOSE_WAIT_WARN", 5)
    assert "CLOSE-WAIT" in (daemonlink.pressure(force=True)["warn"] or "")


def test_tracker_reasserts_after_daemon_restart(fake, monkeypatch):
    monkeypatch.setattr("dashboard.tracking.FACE_POLL_HZ", 20.0)
    monkeypatch.setattr("dashboard.tracking.REASSERT_AFTER_MISSES", 2)
    s = _session(fake)
    tr = Tracker(s.request)
    tr.set_enabled(True)
    assert fake.face_ts is not None
    fake.face_ts = None                               # "daemon restarted": detector gone, we still think enabled
    t0 = time.time()
    while fake.face_ts is None and time.time() - t0 < 3:
        time.sleep(0.05)
    assert fake.face_ts is not None, "tracker never re-enabled the daemon tracker"
    assert tr.reasserts >= 1 and tr.status()["reasserts"] >= 1
    enables = [r for r in fake.requests if r[1] == "/api/media/tracking/enable"]
    assert len(enables) == 2
    tr.stop()


def test_tracker_reassert_method_direct(fake):
    s = _session(fake)
    tr = Tracker(s.request)
    tr.reassert()                                     # not enabled → no calls at all
    assert not [r for r in fake.requests if r[1].startswith("/api/media/tracking")]
    tr.set_enabled(True)
    fake.face_ts = None
    tr.reassert()
    assert fake.face_ts is not None
    tr.stop()


def test_tracker_does_not_reassert_while_paused(fake, monkeypatch):
    """enable weight=0 makes the daemon clear its face target (ts:null) — that is a pause, not a restart."""
    monkeypatch.setattr("dashboard.tracking.FACE_POLL_HZ", 20.0)
    monkeypatch.setattr("dashboard.tracking.REASSERT_AFTER_MISSES", 2)
    s = _session(fake)
    tr = Tracker(s.request)
    tr.set_enabled(True)
    tr.hold("emotion:cheerful1", ttl=5.0)             # → weight 0
    fake.face_ts = None                               # daemon behaviour on weight 0
    time.sleep(0.5)                                   # ~10 polls
    assert tr.reasserts == 0
    enables = [r for r in fake.requests if r[1] == "/api/media/tracking/enable"]
    assert len(enables) == 2                          # enable(1) + hold → enable(0); nothing else
    tr.stop()
