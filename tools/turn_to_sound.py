"""turn_to_sound — let TINY turn its head toward whoever is talking (Direction of Arrival).

Thin toggle over the dashboard's DoA turner (dashboard/doa.py, GET/POST /api/doa). The controller lives in the
dashboard process because the DoA rides the daemon state WebSocket it already keeps open — a persona only flips
the switch. From the robot itself (127.0.0.1) no key is needed (auth.loopback_write); elsewhere REACHY_TOKEN.
"""
from __future__ import annotations

import os
import urllib.error

from strands import tool

from ._reachy_common import err, ok
from .head_tracking import _call, _http_err

DASH = os.getenv("TINY_DASHBOARD_URL", "http://127.0.0.1:8097").rstrip("/")


def _fmt(st: dict) -> str:
    on = "ON" if st.get("enabled") else "OFF"
    ang = st.get("angle_deg")
    where = ""
    if ang is not None:
        d = st.get("delta_deg") or 0.0
        side = "left" if d > 0 else ("right" if d < 0 else "ahead")
        where = f"; last sound {ang:.0f}° ({abs(d):.0f}° to the {side}{', speech' if st.get('speech') else ''})"
    why = f"; waiting: {st['why']}" if st.get("why") and st.get("enabled") else ""
    return f"turn-to-sound {on} ({st.get('turns', 0)} turns so far){where}{why}"


@tool
def turn_to_sound(enabled: bool = True) -> dict:
    """Turn toward whoever is speaking when no face is being tracked (ReSpeaker direction of arrival).

    While ON, TINY turns its head (and body, for sounds far round) toward speech that holds still for ~half a
    second, at most once every 2 s, and only when face tracking has no lock and nothing else is moving the head.
    Face tracking takes over once the speaker is in view. Turn OFF for photo/demo moments where the head must
    stay put.

    Args:
        enabled: True to turn toward speech, False to stop.
    """
    try:
        st = _call("POST", "/api/doa", {"enabled": bool(enabled)})
        return ok(_fmt(st), **{k: st.get(k) for k in ("enabled", "turns", "angle_deg", "why", "sign")})
    except urllib.error.HTTPError as e:
        return err(f"turn_to_sound failed: HTTP {e.code} {_http_err(e)}")
    except Exception as e:  # noqa: BLE001
        return err(f"turn_to_sound failed: {e} (dashboard at {DASH} unreachable)")


@tool
def turn_to_sound_status() -> dict:
    """Is turn-to-sound on, where was the last sound (degrees, left/right), and why is TINY not turning right now?"""
    try:
        st = _call("GET", "/api/doa")
        return ok(_fmt(st), **{k: st.get(k) for k in ("enabled", "turns", "angle_deg", "delta_deg", "speech", "why", "calib")})
    except Exception as e:  # noqa: BLE001
        return err(f"turn_to_sound_status failed: {e}")
