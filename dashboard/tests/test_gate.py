"""The login gate: nothing under /api/* (and /ws) answers without a key, except /api/health and /api/auth/*.

Run: cd dashboard && REACHY_NO_AUTOAPP=1 python -m pytest tests -q
"""
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("REACHY_NO_AUTOAPP", "1")
os.environ["REACHY_TOKEN"] = "test-token-do-not-use"
os.environ["REACHY_RP_ID"] = "reachy.test"
os.environ["REACHY_ASK_PREWARM"] = "0"
os.environ["REACHY_DASH_CAMERA_OFF"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from dashboard import auth  # noqa: E402
from dashboard import server  # noqa: E402

TOKEN = os.environ["REACHY_TOKEN"]


@pytest.fixture(scope="module")
def client():
    auth.configure()
    app = server.create_app()
    # no `with` → startup hooks (camera, agent prewarm) never run
    return TestClient(app, base_url="https://reachy.test")


def test_health_is_public(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_auth_status_is_public(client):
    assert client.get("/api/auth/status").status_code == 200


@pytest.mark.parametrize("path", ["/api/state", "/api/emotions", "/api/log", "/api/snapshot.jpg", "/api/stream",
                                  "/api/telemetry", "/api/camera/snapshot", "/api/ask/last"])
def test_reads_need_login(client, path):
    r = client.get(path)
    assert r.status_code == 401, (path, r.text)
    assert r.json()["error"] == "login required"
    assert r.headers.get("cache-control") == "no-store"


def test_bearer_opens_reads(client):
    r = client.get("/api/state", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200
    assert "motors" in r.json() or isinstance(r.json(), dict)


def test_wrong_bearer_refused(client):
    assert client.get("/api/state", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_stream_accepts_query_token(client):
    # <img src="/api/stream?token=…"> cannot set headers → the gate must read ?token=
    r = client.get("/api/stream?token=" + TOKEN)
    # camera disabled in tests → 503 from the handler, i.e. we got PAST the gate
    assert r.status_code in (200, 503)
    assert r.status_code != 401


def test_stream_accepts_session_cookie(client):
    sid = auth.new_session()
    r = client.get("/api/stream", cookies={auth.SESSION_COOKIE: sid})
    assert r.status_code in (200, 503) and r.status_code != 401


def test_control_still_needs_key(client):
    assert client.post("/api/control/stop").status_code == 401
    assert client.post("/api/control/stop", headers={"Authorization": f"Bearer {TOKEN}"}).status_code != 401


def test_ws_without_key_is_closed(client):
    with client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["who"] is None and hello["error"] == "login required"
        with pytest.raises(Exception):
            ws.receive_json()          # server closed with 4401


def test_ws_with_query_token(client):
    with client.websocket_connect("/ws?token=" + TOKEN) as ws:
        hello = ws.receive_json()
        assert hello["who"] == "token" and hello["can_control"] is True


def test_spa_shell_is_public(client):
    r = client.get("/")
    assert r.status_code == 200


def test_loopback_read_allowance():
    """tools/reachy_camera.py (personas, on the robot) reads /api/snapshot.jpg from 127.0.0.1 without a key —
    but a tunnel request (also from 127.0.0.1, with the public Host / cf-connecting-ip) must NOT pass."""
    from starlette.requests import Request

    def req(headers, host="127.0.0.1", method="GET"):
        scope = {"type": "http", "method": method, "path": "/api/snapshot.jpg", "query_string": b"",
                 "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
                 "client": (host, 1234)}
        return Request(scope)

    assert auth.loopback_read(req({"host": "127.0.0.1:8097"}))
    assert not auth.loopback_read(req({"host": "reachy.cagatay.my"}))
    assert not auth.loopback_read(req({"host": "127.0.0.1:8097", "cf-connecting-ip": "1.2.3.4"}))
    assert not auth.loopback_read(req({"host": "127.0.0.1:8097"}, host="192.168.1.7"))
    assert not auth.loopback_read(req({"host": "127.0.0.1:8097"}, method="POST"))


# ── /api/tracking: gated like every /api route, plus the documented loopback WRITE allowance ──
def test_tracking_anonymous_401(client):
    assert client.get("/api/tracking").status_code == 401
    assert client.post("/api/tracking", json={"enabled": True}).status_code == 401
    assert client.post("/api/tracking/hold", json={"name": "speaking", "on": True}).status_code == 401


def test_tracking_bearer_reads_and_validates(client):
    h = {"Authorization": f"Bearer {TOKEN}"}
    r = client.get("/api/tracking", headers=h)
    assert r.status_code == 200 and "enabled" in r.json()
    # startup hooks never ran in tests → tracker not attached → 502 with a clear reason, never a crash
    r = client.post("/api/tracking", json={"enabled": True}, headers=h)
    assert r.status_code == 502 and "unavailable" in r.json()["detail"]["error"]
    r = client.post("/api/tracking", json={"enabled": "yes"}, headers=h)
    assert r.status_code == 422
    r = client.post("/api/tracking/hold", json={"on": True}, headers=h)
    assert r.status_code == 422


def test_tracking_loopback_write_allowance_is_narrow():
    from starlette.requests import Request as _R

    def req(path, method="POST", host="127.0.0.1:8097", client=("127.0.0.1", 1), extra=()):
        headers = [(b"host", host.encode())] + [(k.encode(), v.encode()) for k, v in extra]
        return _R({"type": "http", "method": method, "path": path, "headers": headers, "client": client,
                   "query_string": b"", "scheme": "http", "server": ("127.0.0.1", 8097)})

    assert auth.loopback_write(req("/api/tracking"))
    assert auth.loopback_write(req("/api/tracking/hold"))
    assert not auth.loopback_write(req("/api/control/look"))                        # only the tracking routes
    assert not auth.loopback_write(req("/api/tracking", host="reachy.cagatay.my"))  # tunnel Host
    assert not auth.loopback_write(req("/api/tracking", extra=[("cf-connecting-ip", "1.2.3.4")]))
    assert not auth.loopback_write(req("/api/tracking", client=("192.168.1.9", 1)))
    assert not auth.loopback_write(req("/api/tracking", method="GET"))
