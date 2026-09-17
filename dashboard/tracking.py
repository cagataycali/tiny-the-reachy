"""Face tracking — DAEMON EDITION (reachy-mini ≥ 1.10.0).

We do NOT detect faces ourselves. The daemon runs a YuNet detector on its own camera pipeline
(reachy_mini.vision.face_tracking) and blends the head toward the face every control tick:

    POST /api/media/tracking/enable  {"weight": 0..1}   weight 1 = tracking owns the head,
                                                         weight 0 = detector paused, head free
    POST /api/media/tracking/disable                     detector thread stopped, aim cleared
    GET  /api/media/tracking/face  → {"face_target": {detected, x, y, roll, ts}}  x,y ∈ [-1, 1]

Two hard facts drive this module:

1. The daemon's tracker reads frames over the daemon's IPC camera socket, so the DAEMON must own
   the sensor. Anything that releases media (SDK clients with media_backend="no_media",
   voice_listener's POST /api/media/release) kills tracking AND the IPC feed → the dashboard's
   `ipc` camera backend (robot.Camera) re-acquires media whenever the socket disappears.
2. While the daemon tracks at weight ≥ 1 it IGNORES set_target_head_pose (goto/emotions/looks get
   overridden). Pollen's conversation app therefore pauses tracking (weight 0.0) while the robot
   speaks or plays a move and hands the head back (weight 1.0) afterwards. `Tracker` does the same
   with named HOLDS: hold("speaking") / hold("emotion:cheerful1") / hold("look") … release(name).
   Any live hold → weight 0.0; no holds → weight 1.0. Holds expire on their own (ttl) so a crashed
   persona can never freeze the head.

The dashboard is the one long-lived process every persona can reach (127.0.0.1:8097), so the
controller lives here; tools/head_tracking.py is a thin REST toggle over it (Pollen's 6-line tool).
Default ON at boot (REACHY_TRACK_AUTOSTART=1, server.py); REACHY_TRACK_AUTOSTART=0 to start off.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable, Dict, Optional

log = logging.getLogger("reachy.dash.tracking")

FACE_POLL_HZ = float(os.getenv("REACHY_TRACK_POLL_HZ", "2"))          # get_tracked_face poll (≤ 2 Hz — daemon pressure, 2026-09-17)
REASSERT_AFTER_MISSES = int(os.getenv("REACHY_TRACK_REASSERT_MISSES", "2"))  # ts:null polls while we think enabled → daemon restarted
HOLD_TTL_DEFAULT = float(os.getenv("REACHY_TRACK_HOLD_TTL", "20"))    # a hold nobody releases dies after this
SPEAK_HOLD = "speaking"

DaemonFn = Callable[..., Any]   # daemon(method, path, body=None, timeout=4.0)


class Tracker:
    """Owns the daemon's tracking state: enabled flag, weight, holds, latest face. Thread-safe."""

    def __init__(self, daemon: DaemonFn, on_change: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
        self._daemon = daemon
        self._on_change = on_change
        self._lock = threading.RLock()
        self.enabled = False
        self.weight: Optional[float] = None          # last weight the daemon accepted (None = never enabled)
        self.available: Optional[bool] = None        # daemon said enabled:true (has camera) / false (no camera)
        self.error: Optional[str] = None
        self.face: Dict[str, Any] = {"detected": False, "x": None, "y": None, "roll": None, "ts": None}
        self.face_seen_at: float = 0.0
        self.since: float = 0.0
        self._holds: Dict[str, float] = {}           # name → expiry (monotonic)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_emit: Optional[tuple] = None
        self._misses = 0                             # consecutive face polls with ts:null while enabled
        self.speaking_until = 0.0                    # monotonic; set by hold("speaking") even when no face is locked
        self.reasserts = 0

    # ── daemon calls ──
    def _set_weight(self, w: float) -> bool:
        r = self._daemon("POST", "/api/media/tracking/enable", {"weight": float(w)}, timeout=4)
        ok = bool((r or {}).get("enabled"))
        self.available = ok
        if ok:
            self.weight = float(w)
            self.error = None
        else:
            self.error = "daemon has no camera (media released?) — tracking unavailable"
        return ok

    def _disable(self) -> None:
        self._daemon("POST", "/api/media/tracking/disable", None, timeout=4)
        self.weight = None

    def _apply(self) -> None:
        """Push the weight the holds imply. Caller holds the lock."""
        if not self.enabled:
            return
        want = 0.0 if self._live_holds() else 1.0
        if self.weight != want:
            self._set_weight(want)

    def _live_holds(self) -> Dict[str, float]:
        now = time.monotonic()
        self._holds = {k: v for k, v in self._holds.items() if v > now}
        return self._holds

    # ── public API ──
    def set_enabled(self, on: bool, who: str = "dashboard") -> Dict[str, Any]:
        with self._lock:
            on = bool(on)
            if on and not self.enabled:
                self.enabled = True
                self.since = time.time()
                try:
                    ok = self._set_weight(0.0 if self._live_holds() else 1.0)
                except RuntimeError as e:
                    self.enabled = False
                    self.error = str(e)[:300]
                    raise
                if not ok:
                    self.enabled = False
                    raise RuntimeError(self.error or "tracking unavailable")
                self._start()
            elif not on and self.enabled:
                self.enabled = False
                try:
                    self._disable()
                except RuntimeError as e:
                    self.error = str(e)[:300]
                    log.warning("tracking disable: %s", e)
                self.face = {"detected": False, "x": None, "y": None, "roll": None, "ts": None}
            # idempotent otherwise
            st = self.status()
        self._emit(st, force=True)
        return st

    def hold(self, name: str, ttl: float = HOLD_TTL_DEFAULT, who: str = "dashboard") -> Dict[str, Any]:
        """Pause tracking (weight 0) while `name` is held. Speaking holds only bite once a face is locked
        (Pollen: 'pause only once a face is locked, else speech blocks acquisition')."""
        with self._lock:
            if name == SPEAK_HOLD:
                # remembered independently of the weight rule below: the DoA turner must never chase TINY's own voice
                self.speaking_until = time.monotonic() + max(0.5, min(float(ttl), 120.0))
            if name == SPEAK_HOLD and not self.face.get("detected") and not self._holds.get(name):
                return self.status()
            self._holds[name] = time.monotonic() + max(0.5, min(float(ttl), 120.0))
            try:
                self._apply()
            except RuntimeError as e:
                self.error = str(e)[:300]
            st = self.status()
        self._emit(st)
        return st

    def is_speaking(self, tail_s: float = 0.0) -> bool:
        """True while a 'speaking' hold is live (or within tail_s after it ended) — regardless of face lock."""
        return time.monotonic() < self.speaking_until + tail_s

    def release(self, name: str, who: str = "dashboard") -> Dict[str, Any]:
        with self._lock:
            if name == SPEAK_HOLD:
                self.speaking_until = min(self.speaking_until, time.monotonic())
            self._holds.pop(name, None)
            try:
                self._apply()
            except RuntimeError as e:
                self.error = str(e)[:300]
            st = self.status()
        self._emit(st)
        return st

    def status(self) -> Dict[str, Any]:
        with self._lock:
            holds = sorted(self._live_holds())
            return {"enabled": self.enabled, "weight": self.weight, "paused": bool(holds) and self.enabled,
                    "holds": holds, "available": self.available, "error": self.error,
                    "detected": bool(self.face.get("detected")), "x": self.face.get("x"), "y": self.face.get("y"),
                    "roll": self.face.get("roll"), "face_ts": self.face.get("ts"),
                    "face_age_s": round(time.time() - self.face_seen_at, 1) if self.face_seen_at else None,
                    "since": self.since or None, "engine": "daemon-yunet", "poll_hz": FACE_POLL_HZ,
                    "reasserts": self.reasserts}

    def adopt(self) -> bool:
        """Startup: if the daemon is ALREADY tracking (we were restarted, or someone enabled it directly), mirror it
        instead of pretending it is off. The daemon has no 'enabled' getter — its face `ts` is non-null iff the
        detector is running. Returns True when adopted."""
        try:
            r = self._daemon("GET", "/api/media/tracking/face", None, timeout=3)
        except RuntimeError as e:
            self.error = str(e)[:300]
            return False
        ft = (r or {}).get("face_target") or {}
        if ft.get("ts") is None:
            return False
        with self._lock:
            if self.enabled:
                return True
            self.enabled, self.since, self.available = True, time.time(), True
            self.weight = 1.0                       # unknown really; the first _apply() re-asserts from our holds
            self.face = {"detected": bool(ft.get("detected")), "x": ft.get("x"), "y": ft.get("y"),
                         "roll": ft.get("roll"), "ts": ft.get("ts")}
            try:
                self._set_weight(0.0 if self._live_holds() else 1.0)
            except RuntimeError as e:
                self.error = str(e)[:300]
            self._start()
            st = self.status()
        log.info("tracking: adopted the daemon's running tracker")
        self._emit(st, force=True)
        return True

    def stop(self) -> None:
        """Persona/dashboard shutdown: stop tracking cleanly (Pollen moves.py ~661)."""
        self._stop.set()
        with self._lock:
            if self.enabled:
                self.enabled = False
                try:
                    self._disable()
                except RuntimeError as e:
                    log.warning("tracking disable on shutdown: %s", e)

    # ── face poll (≤ FACE_POLL_HZ while enabled) ──
    def _start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="face-poll", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        period = 1.0 / max(0.5, FACE_POLL_HZ)
        while not self._stop.is_set():
            if not self.enabled:
                self._stop.wait(0.5)
                continue
            t = time.monotonic()
            try:
                r = self._daemon("GET", "/api/media/tracking/face", None, timeout=2)
                ft = (r or {}).get("face_target") or {}
                with self._lock:
                    self.face = {"detected": bool(ft.get("detected")), "x": ft.get("x"), "y": ft.get("y"),
                                 "roll": ft.get("roll"), "ts": ft.get("ts")}
                    if self.face["detected"]:
                        self.face_seen_at = time.time()
                    # ts is None when the daemon's detector is OFF — or PAUSED (enable weight=0 calls
                    # clear_tracking_aim(), backend/abstract.py). Only when we expect weight 1 (no holds) does a
                    # null ts mean the daemon restarted under us / someone disabled it → re-assert instead of
                    # showing a tracking pill that lies. (05:58 BST: 43 false re-asserts during emotion holds.)
                    if ft.get("ts") is None and self.enabled and self.weight == 1.0 and not self._live_holds():
                        self._misses += 1
                        if self._misses >= REASSERT_AFTER_MISSES:
                            self._misses = 0
                            self._reassert_locked()
                    else:
                        self._misses = 0
                    # a hold that expired while we slept → hand the head back
                    self._apply()
                    st = self.status()
                self._emit(st)
            except RuntimeError as e:
                with self._lock:
                    self.error = str(e)[:300]
            self._stop.wait(max(0.0, period - (time.monotonic() - t)))

    def _reassert_locked(self) -> None:
        """Daemon came back without our tracker: push the weight again (caller holds the lock)."""
        try:
            want = 0.0 if self._live_holds() else 1.0
            ok = self._set_weight(want)
            self.reasserts += 1
            log.info("tracking: re-asserted after daemon restart (weight %.0f, ok=%s)", want, ok)
        except RuntimeError as e:
            self.error = str(e)[:300]

    def reassert(self) -> None:
        """Stream reconnected / daemon restarted: re-enable if we were enabled (retries while media comes up)."""
        for _ in range(10):
            with self._lock:
                if not self.enabled:
                    return
                try:
                    r = self._daemon("GET", "/api/media/tracking/face", None, timeout=3)
                except RuntimeError:
                    r = None
                if r is not None:
                    if ((r or {}).get("face_target") or {}).get("ts") is None and not self._live_holds():
                        self._reassert_locked()
                        if self.available:
                            return
                    else:
                        return
            time.sleep(3)

    def _emit(self, st: Dict[str, Any], force: bool = False) -> None:
        if not self._on_change:
            return
        key = (st["enabled"], st["paused"], st["detected"],
               None if st["x"] is None else round(st["x"], 2), None if st["y"] is None else round(st["y"], 2))
        if force or key != self._last_emit:
            self._last_emit = key
            try:
                self._on_change({"type": "tracking", **st})
            except Exception as e:  # noqa: BLE001
                log.debug("tracking emit: %s", e)
