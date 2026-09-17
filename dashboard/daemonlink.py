"""daemonlink — how the dashboard talks to the reachy-mini daemon WITHOUT hurting it.

Why this exists (incident 2026-09-17 05:29 BST): the daemon hit EMFILE — 1024/1024 fds, 614 sockets on :8000 in
CLOSE-WAIT, 109 % CPU; camera/tracking/DoA dead for 10 min. A 60 s census showed the dashboard alone making
485 GET /api/state/full + 485 GET /api/move/running + 300 GET /api/media/tracking/face per minute, each on a
fresh urllib connection (≈21 new TCP connections/s) against a CM4 that is also running YuNet + DoA + video.

Contract:
  * `Session` — ONE keep-alive requests.Session (urllib3 pool) for every REST call. `request()` mirrors the old
    robot.daemon() signature/errors so nothing else changes.
  * `StateStream` — ONE persistent WebSocket to the daemon's /api/state/ws/full (10 Hz, with_doa) shared by every
    consumer (WS pump, /api/state, tracker, DoA turner). Reconnects with back-off; while it is down, `latest()`
    falls back to a rate-limited REST poll (≤ 4 Hz), never a burst.
  * `MovesProbe` — /api/move/running only while a move can be in flight (we started one, or the last probe saw
    one); otherwise a 3 s heartbeat so an emotion fired by a persona still shows up as a chip.
  * `pressure()` — the daemon's fd count / limit + CLOSE-WAIT and ESTABLISHED sockets on :8000, cached 5 s, for
    /api/health and the cockpit warning pill.

Nothing here touches motors.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter

log = logging.getLogger("reachy.dash.daemonlink")

DAEMON = os.getenv("REACHY_DAEMON_URL", "http://127.0.0.1:8000").rstrip("/")
STREAM_HZ = float(os.getenv("REACHY_DAEMON_STREAM_HZ", "10"))          # the daemon's own cap is what we ask for
FALLBACK_HZ = float(os.getenv("REACHY_DAEMON_FALLBACK_HZ", "4"))       # REST poll while the stream is down
STREAM_STALE_S = float(os.getenv("REACHY_DAEMON_STREAM_STALE_S", "1.5"))
MOVES_IDLE_S = float(os.getenv("REACHY_MOVES_IDLE_PROBE_S", "3"))     # heartbeat when nothing is in flight
MOVES_ACTIVE_HZ = float(os.getenv("REACHY_MOVES_ACTIVE_HZ", "5"))
PRESSURE_TTL_S = 5.0
FD_WARN_FRACTION = float(os.getenv("REACHY_FD_WARN_FRACTION", "0.6"))
CLOSE_WAIT_WARN = int(os.getenv("REACHY_CLOSE_WAIT_WARN", "50"))


# ── one keep-alive session ─────────────────────────────────────────────────────
class Session:
    """requests.Session with a small pool. urllib3's pool is thread-safe, so one instance serves every thread."""

    def __init__(self, base: str = DAEMON) -> None:
        self.base = base
        self.s = requests.Session()
        ad = HTTPAdapter(pool_connections=2, pool_maxsize=8, max_retries=0)
        self.s.mount("http://", ad)
        self.s.headers["Connection"] = "keep-alive"
        self.calls = 0
        self.errors = 0

    def request(self, method: str, path: str, body: Optional[dict] = None, timeout: float = 4.0) -> Any:
        """Same contract as the old robot.daemon(): JSON in/out, RuntimeError with the daemon's message on failure."""
        self.calls += 1
        try:
            r = self.s.request(method, self.base + path, json=body if body is not None else None, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout, OSError) as e:
            self.errors += 1
            raise RuntimeError(f"daemon unreachable ({path}): {e}") from None
        if r.status_code >= 400:
            self.errors += 1
            try:
                detail = r.json()
            except ValueError:
                detail = r.reason
            raise RuntimeError(f"daemon {method} {path} → {r.status_code}: {detail}")
        if not r.content:
            return None
        try:
            return r.json()
        except ValueError:
            return None

    def close(self) -> None:
        try:
            self.s.close()
        except Exception:  # noqa: BLE001
            pass


SESSION = Session()


def daemon(method: str, path: str, body: Optional[dict] = None, timeout: float = 4.0) -> Any:
    return SESSION.request(method, path, body, timeout)


# ── the state stream ───────────────────────────────────────────────────────────
STREAM_FIELDS = {
    "with_head_pose": "true", "with_body_yaw": "true", "with_antenna_positions": "true",
    "with_head_joints": "true", "with_target_head_joints": "true", "with_target_body_yaw": "true",
    "with_target_antenna_positions": "true", "with_doa": "true",
    # NOT with_target_head_pose: the daemon asserts target_pose is not None → 500 / skipped frames until the
    # first goto after boot (140× "assert target_pose is not None" seen after the 05:38 restart). The twin's
    # ghost uses target_head_joints, which is always populated.
}


class StateStream:
    """Latest /api/state/full frame from the daemon's WebSocket, or a slow REST fallback. Thread-safe."""

    def __init__(self, session: Session = SESSION, on_frame: Optional[Callable[[dict], None]] = None) -> None:
        self.session = session
        self.on_frame = on_frame
        self.on_connect: Optional[Callable[[], None]] = None   # fired (in a helper thread) after every (re)connect
        self.listeners: list = []                             # extra per-frame consumers (DoA turner, IMU watch)
        self._frame: Optional[dict] = None
        self._at = 0.0                      # monotonic time of the last frame (stream or fallback)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.connected = False
        self.frames = 0
        self.reconnects = 0
        self.error: Optional[str] = None
        self._last_fallback = 0.0
        self._fallback_lock = threading.Lock()

    # lifecycle
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="daemon-state-stream", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def url(self) -> str:
        ws_base = self.session.base.replace("http://", "ws://", 1).replace("https://", "wss://", 1)
        q = dict(STREAM_FIELDS, frequency=f"{STREAM_HZ:g}")
        return f"{ws_base}/api/state/ws/full?{urlencode(q)}"

    def _run(self) -> None:
        try:
            from websockets.sync.client import connect  # noqa: PLC0415
        except Exception as e:  # noqa: BLE001 — no websockets lib → REST fallback only
            self.error = f"websockets unavailable ({e}); REST fallback only"
            log.warning("state stream: %s", self.error)
            return
        backoff = 1.0
        while not self._stop.is_set():
            try:
                with connect(self.url, open_timeout=5, close_timeout=1, max_size=1 << 20) as ws:
                    self.connected, self.error, backoff = True, None, 1.0
                    log.info("state stream: connected (%s Hz)", f"{STREAM_HZ:g}")
                    if self.on_connect:
                        threading.Thread(target=self.on_connect, name="stream-on-connect", daemon=True).start()
                    while not self._stop.is_set():
                        raw = ws.recv(timeout=max(2.0, 3.0 / STREAM_HZ))
                        frame = json.loads(raw)
                        if not isinstance(frame, dict):
                            continue
                        with self._lock:
                            self._frame, self._at = frame, time.monotonic()
                            self.frames += 1
                        for fn in ([self.on_frame] if self.on_frame else []) + list(self.listeners):
                            try:
                                fn(frame)
                            except Exception as e:  # noqa: BLE001
                                log.debug("frame listener %s: %s", getattr(fn, "__qualname__", fn), e)
            except Exception as e:  # noqa: BLE001 — connection refused / timeout / daemon restart
                if self.connected:
                    self.reconnects += 1
                self.error = str(e)[:200]
                log.info("state stream: down (%s) — retry in %.0fs", self.error, backoff)
            finally:
                self.connected = False
            self._stop.wait(backoff)
            backoff = min(backoff * 2, 5.0)

    # reads
    def age(self) -> Optional[float]:
        with self._lock:
            return None if self._frame is None else time.monotonic() - self._at

    def latest(self, max_age: float = STREAM_STALE_S) -> Tuple[Optional[dict], Optional[float]]:
        """(frame, age_s). Falls back to ONE REST GET at ≤ FALLBACK_HZ when the stream has nothing fresh."""
        with self._lock:
            frame, at = self._frame, self._at
        now = time.monotonic()
        if frame is not None and now - at <= max_age:
            return frame, now - at
        # stream stale/down → rate-limited REST poll (raise like the stream would be silent otherwise)
        with self._fallback_lock:
            if now - self._last_fallback < 1.0 / max(0.5, FALLBACK_HZ):
                if frame is not None:
                    return frame, now - at
                raise RuntimeError(self.error or "daemon state stream not connected yet")
            self._last_fallback = now
        got = self.session.request("GET", "/api/state/full?" + urlencode(STREAM_FIELDS), timeout=2)
        if isinstance(got, dict):
            with self._lock:
                self._frame, self._at = got, time.monotonic()
            return got, 0.0
        raise RuntimeError("daemon state/full returned nothing")

    def status(self) -> Dict[str, Any]:
        age = self.age()
        return {"connected": self.connected, "hz": STREAM_HZ, "frames": self.frames, "reconnects": self.reconnects,
                "age_s": None if age is None else round(age, 2), "error": self.error}


# ── move/running only when it matters ──────────────────────────────────────────
class MovesProbe:
    def __init__(self, session: Session = SESSION) -> None:
        self.session = session
        self._running: list = []
        self._at = 0.0
        self._armed_until = 0.0
        self._lock = threading.Lock()

    def arm(self, seconds: float = 10.0) -> None:
        """We just started a move: probe at MOVES_ACTIVE_HZ for a while."""
        with self._lock:
            self._armed_until = max(self._armed_until, time.monotonic() + seconds)

    def running(self) -> list:
        now = time.monotonic()
        with self._lock:
            active = now < self._armed_until or bool(self._running)
            period = 1.0 / MOVES_ACTIVE_HZ if active else MOVES_IDLE_S
            if now - self._at < period:
                return self._running
            self._at = now
        try:
            got = self.session.request("GET", "/api/move/running", timeout=2) or []
        except RuntimeError:
            got = []
        with self._lock:
            self._running = list(got) if isinstance(got, list) else []
            return self._running


# ── daemon pressure gauge ──────────────────────────────────────────────────────
_pressure_cache: Dict[str, Any] = {"t": 0.0, "v": None}
_pressure_lock = threading.Lock()


def _daemon_pid() -> Optional[int]:
    try:
        out = subprocess.run(["pgrep", "-f", "reachy_mini.daemon.app.main"], capture_output=True, text=True, timeout=3).stdout
        pids = [int(p) for p in out.split() if p.strip().isdigit()]
        return pids[0] if pids else None
    except Exception:  # noqa: BLE001
        return None


def _sock_count(state: str, port: int = 8000) -> Optional[int]:
    try:
        out = subprocess.run(["ss", "-Htan", "state", state, f"( sport = :{port} )"],
                             capture_output=True, text=True, timeout=3).stdout
        return len([ln for ln in out.splitlines() if ln.strip()])
    except Exception:  # noqa: BLE001
        return None


def pressure(force: bool = False) -> Dict[str, Any]:
    """fds/limit of the daemon process (same user, /proc readable), CLOSE-WAIT + ESTABLISHED on :8000, our own
    call counters. `warn` is a short human string or None."""
    with _pressure_lock:
        now = time.monotonic()
        if not force and _pressure_cache["v"] is not None and now - _pressure_cache["t"] < PRESSURE_TTL_S:
            return _pressure_cache["v"]
        pid = _daemon_pid()
        fds = limit = None
        if pid:
            try:
                fds = len(os.listdir(f"/proc/{pid}/fd"))
            except OSError:
                fds = None
            try:
                with open(f"/proc/{pid}/limits") as f:
                    for ln in f:
                        if ln.startswith("Max open files"):
                            limit = int(ln.split()[3])
            except (OSError, ValueError, IndexError):
                limit = None
        cw, est = _sock_count("close-wait"), _sock_count("established")
        warn = None
        if fds is not None and limit and fds >= FD_WARN_FRACTION * limit:
            warn = f"daemon fds {fds}/{limit}"
        if cw is not None and cw >= CLOSE_WAIT_WARN:
            warn = (warn + " · " if warn else "") + f"{cw} CLOSE-WAIT on :8000"
        v = {"pid": pid, "fds": fds, "fd_limit": limit, "close_wait": cw, "established": est, "warn": warn,
             "session_calls": SESSION.calls, "session_errors": SESSION.errors, "t": time.time()}
        _pressure_cache.update(t=now, v=v)
        return v
