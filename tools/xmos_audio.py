"""XVF3800 (Reachy Mini Audio board) post-processing knobs the voice persona needs.

MEASURED 2026-09-18 on the Wireless (firmware 2.1.2, owner counting aloud from his chair while
7.6 s of TTS played through the speaker, `reachymini_audio_src` recorded):

    PP_NLATTENONOFF=1 (factory)  voice -43 dBFS → -75 dBFS the instant the robot spoke: the
                                 non-linear residual-echo attenuator MUTES the near end while
                                 the far end is active. OpenAI never hears you → no barge-in.
    PP_NLATTENONOFF=0            suppression 17 dB → 4 dB; barge-in confirmed by the owner.
                                 Cost: residual echo of the robot's own voice rises from
                                 -63 dBFS (peak -37) to -47 dBFS (peak -25) — still ~15 dB
                                 under normal speech, the linear AEC keeps doing its job.

The setting is RUNTIME-ONLY on the chip (a power cycle restores the factory value and Pollen's
daemon does not re-apply anything), so the voice persona writes it at every start. Nothing is
saved to the board's flash (SAVE_CONFIGURATION is deliberately never sent).

Two write paths, daemon-first:
  1. POST http://REACHY_HOST:REACHY_PORT/api/audio/config/apply  — Pollen's endpoint; on daemon
     1.10.0 it answers {"applied": false} for int32 parameters because the request model casts
     values to float and the USB writer then fails with "required argument is not an integer"
     (reported upstream). When it starts working, it wins.
  2. /venvs/mini_daemon/bin/python -m reachy_mini.media.audio_control_utils NAME --values V —
     the same USB control transfer Pollen's tool uses, from the daemon's venv (pyusb lives
     there). Works alongside the daemon holding the audio interfaces.

Env: VOICE_XMOS_PARAMS="PP_NLATTENONOFF=0" (default on a Wireless; comma-separated NAME=V pairs;
empty string disables). Verified by reading the parameter back.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from typing import Dict, List, Tuple

DEFAULT_PARAMS = "PP_NLATTENONOFF=0"
DAEMON_PYTHON = os.getenv("REACHY_DAEMON_PYTHON", "/venvs/mini_daemon/bin/python")


def parse_params(spec: str | None) -> List[Tuple[str, float]]:
    """'A=1, B=0.5' → [('A', 1.0), ('B', 0.5)]; bad pairs are skipped, never raise."""
    out: List[Tuple[str, float]] = []
    for pair in (spec or "").split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        name, _, val = pair.partition("=")
        name = name.strip().upper()
        try:
            out.append((name, float(val.strip())))
        except ValueError:
            continue
    return out


def _daemon_base() -> str:
    return f"http://{os.getenv('REACHY_HOST', 'localhost')}:{os.getenv('REACHY_PORT', '8000')}"


def read_param(name: str, timeout: float = 5.0) -> List[float] | None:
    try:
        with urllib.request.urlopen(f"{_daemon_base()}/api/audio/config/parameter/{name}", timeout=timeout) as r:
            return list(json.loads(r.read().decode())["values"])
    except Exception:  # noqa: BLE001
        return None


def _write_via_daemon(name: str, value: float, timeout: float = 10.0) -> bool:
    body = json.dumps({"config": [{"name": name, "values": [value]}], "verify": True}).encode()
    req = urllib.request.Request(f"{_daemon_base()}/api/audio/config/apply", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return bool(json.loads(r.read().decode()).get("applied"))
    except Exception:  # noqa: BLE001
        return False


def _write_via_usb(name: str, value: float, timeout: float = 60.0) -> bool:
    if not os.path.exists(DAEMON_PYTHON):
        return False
    val = str(int(value)) if float(value).is_integer() else str(value)
    try:
        p = subprocess.run([DAEMON_PYTHON, "-m", "reachy_mini.media.audio_control_utils", name, "--values", val],
                           capture_output=True, text=True, timeout=timeout)
    except Exception:  # noqa: BLE001
        return False
    return p.returncode == 0 and "completed successfully" in (p.stdout + p.stderr)


def apply_params(spec: str | None = None, log=print) -> Dict[str, str]:
    """Apply NAME=V pairs; returns {name: 'ok'|'already'|'failed'|'unverified'}."""
    if spec is None:
        spec = os.getenv("VOICE_XMOS_PARAMS", DEFAULT_PARAMS)
    results: Dict[str, str] = {}
    for name, value in parse_params(spec):
        before = read_param(name)
        if before is not None and before and float(before[0]) == value:
            results[name] = "already"
            continue
        ok = _write_via_daemon(name, value) or _write_via_usb(name, value)
        after = read_param(name)
        if after is not None and after and float(after[0]) == value:
            results[name] = "ok"
        else:
            results[name] = "failed" if not ok else "unverified"
        log(f"[voice] XVF3800 {name}: {before} → {after} ({results[name]})", file=sys.stderr)
    return results
