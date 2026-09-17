"""TINY head-tracking tools — follow the user's face (Pollen's `head_tracking` tool, daemon edition).

reachy-mini ≥ 1.10 runs the face detector INSIDE the daemon (YuNet on its own camera pipeline) and blends
the head toward the face. We never detect anything ourselves. The controller that owns the on/off state
and the "pause while speaking / moving" holds is dashboard/tracking.py (reachy-dashboard.service, the one
long-lived process every persona can reach); these tools are the thin toggle every persona shares, exactly
like reachy_mini_conversation_app/tools/head_tracking.py: POST /api/tracking on the dashboard. From the
robot itself (127.0.0.1) that route is allowed without a key (dashboard/auth.loopback_write); from anywhere
else set REACHY_TOKEN / TINY_DASHBOARD_TOKEN.

Also here: `SpeakingHandoff` — a Strands `BidiOutput` for the voice persona that pauses tracking
(weight 0.0) while TINY's speech audio streams and hands the head back (weight 1.0) afterwards, the way
Pollen's MovementManager.set_speaking does. Wired in voice_listener.py.
"""
import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request

from strands import tool

from ._reachy_common import ok, err

DASH = os.getenv("TINY_DASHBOARD_URL", "http://127.0.0.1:8097").rstrip("/")
SPEAK_TAIL_S = float(os.getenv("REACHY_SPEAK_TAIL_S", "0.8"))   # playback lags the last audio chunk


def _call(method: str, path: str = "/api/tracking", body: dict | None = None, timeout: float = 6.0) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    rq = urllib.request.Request(f"{DASH}{path}", data=data, method=method,
                                headers={"Content-Type": "application/json"} if data else {})
    tok = os.getenv("TINY_DASHBOARD_TOKEN") or os.getenv("REACHY_TOKEN")
    if tok:
        rq.add_header("Authorization", f"Bearer {tok}")
    with urllib.request.urlopen(rq, timeout=timeout) as r:
        return json.loads(r.read().decode() or "{}")


def _http_err(e: urllib.error.HTTPError) -> str:
    try:
        d = json.loads(e.read().decode()).get("detail", {})
        return d.get("error", "") if isinstance(d, dict) else str(d)
    except Exception:  # noqa: BLE001
        return ""


def _fmt(st: dict) -> str:
    if st.get("available") is False:
        return f"face tracking unavailable on this robot: {st.get('error')}"
    if st.get("detected"):
        face = f"face locked at x={st.get('x'):+.2f} y={st.get('y'):+.2f} (camera frame, [-1,1])"
    else:
        age = st.get("face_age_s")
        face = f"no face in view (last seen {age:.0f}s ago)" if age else "no face in view yet"
    extra = f" — paused while {', '.join(st['holds'])}" if st.get("paused") and st.get("holds") else ""
    return f"head tracking {'ON' if st.get('enabled') else 'OFF'} (daemon YuNet): {face}{extra}"


@tool
def head_tracking(enabled: bool = True) -> dict:
    """Enable or disable following the user's face with the head.

    Use when asked to follow, keep looking at, look at me, track me, or stop following the user.
    The robot's daemon keeps the closest face centred in the camera; it pauses by itself while TINY
    is speaking or playing an emotion/look and drifts back to neutral a couple of seconds after the
    face is gone. Idempotent — calling it with the current state is fine.

    Args:
        enabled: True to start following the user's face, False to stop.
    """
    try:
        r = _call("POST", body={"enabled": bool(enabled)})
    except urllib.error.HTTPError as e:
        return err(f"head_tracking failed: HTTP {e.code} {_http_err(e) or e.reason} (is reachy-dashboard running?)")
    except Exception as e:  # noqa: BLE001
        return err(f"head_tracking failed: {e} (dashboard at {DASH} unreachable)")
    st = r.get("tracking", {})
    return ok(("following" if enabled else "stopped following") + " — " + _fmt(st), **st)


@tool
def head_tracking_status() -> dict:
    """Is TINY following a face right now? Returns enabled/paused, whether a face is detected and where."""
    try:
        st = _call("GET")
    except Exception as e:  # noqa: BLE001
        return err(f"head_tracking_status failed: {e}")
    return ok(_fmt(st), **st)


def tracking_hold(name: str, on: bool, ttl: float = 20.0) -> bool:
    """Pause (on=True → weight 0) or resume (on=False → weight 1) daemon tracking under `name`.
    Best effort, never raises — a persona must never die because the dashboard is down."""
    try:
        _call("POST", "/api/tracking/hold", {"name": name, "on": bool(on), "ttl": float(ttl)}, timeout=3)
        return True
    except Exception:  # noqa: BLE001
        return False


def stop_head_tracking() -> None:
    """Persona shutdown hook (Pollen moves.py ~661): switch tracking off if it is on. Best effort."""
    try:
        if _call("GET", timeout=2).get("enabled"):
            _call("POST", body={"enabled": False}, timeout=3)
    except Exception:  # noqa: BLE001
        pass


class SpeakingHandoff:
    """`BidiOutput`: while the model streams speech audio → tracking hold "speaking" (weight 0.0 once a face
    is locked); on response complete / interruption → release (weight 1.0) after a short playback tail.
    Cheap: one loopback POST at speech start, one at the end; audio chunks in between are not forwarded."""

    def __init__(self, tail_s: float = SPEAK_TAIL_S):
        self.tail_s = tail_s
        self.speaking = False
        self._release_task = None
        self._last_audio = 0.0

    async def start(self, agent) -> None:  # noqa: ARG002
        return None

    async def stop(self) -> None:
        self._set(False, immediate=True)

    def _set(self, speaking: bool, immediate: bool = False) -> None:
        if speaking:
            if self._release_task:
                self._release_task.cancel()
                self._release_task = None
            if not self.speaking:
                self.speaking = True
                tracking_hold("speaking", True, ttl=30.0)
        elif self.speaking:
            if immediate or self.tail_s <= 0:
                self.speaking = False
                tracking_hold("speaking", False)
            elif self._release_task is None:
                async def _later():
                    try:
                        await asyncio.sleep(self.tail_s)
                        self.speaking = False
                        await asyncio.to_thread(tracking_hold, "speaking", False)
                    finally:
                        self._release_task = None
                try:
                    self._release_task = asyncio.get_running_loop().create_task(_later())
                except RuntimeError:
                    self.speaking = False
                    tracking_hold("speaking", False)

    async def __call__(self, event) -> None:
        try:
            t = event.get("type") if isinstance(event, dict) else None
            if t == "bidi_audio_stream":
                now = time.monotonic()
                if not self.speaking:
                    await asyncio.to_thread(self._set, True)
                elif now - self._last_audio > 20:              # long answer: refresh the 30 s hold
                    await asyncio.to_thread(tracking_hold, "speaking", True, 30.0)
                self._last_audio = now
            elif t in ("bidi_response_complete", "bidi_interruption", "bidi_connection_close"):
                self._set(False, immediate=(t != "bidi_response_complete"))
        except Exception as e:  # noqa: BLE001
            print(f"[head_tracking] speaking handoff: {e}", file=sys.stderr)
