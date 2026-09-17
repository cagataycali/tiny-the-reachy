"""doa — turn toward whoever is talking (Direction of Arrival → head/body yaw).

Owner's ask (2026-09-17): "when I speak the Reachy should turn its head to me when face tracking has no lock".

Source of truth: the daemon's ReSpeaker DoA, already inside every frame of the state WebSocket we keep open
(daemonlink.StateStream asks for with_doa=true) → NO extra polling. Pollen's convention (reachy_mini/media/
audio_doa.py): angle in radians, 0 = left, π/2 = front/back, π = right. A linear 4-mic array cannot tell front
from back, so the angle is a LEFT/RIGHT yaw delta: delta = SIGN · (π/2 − angle).

Rules (all must hold before a turn):
  * enabled (REACHY_DOA_TURN=1 default — the owner asked for it explicitly)
  * speech_detected on ≥ MIN_CONSEC consecutive frames whose angles agree within ±TOL_DEG
  * the face tracker has NO lock (a detected face younger than FACE_FRESH_S wins — the tracker is better)
  * no live tracker hold (speaking / emotion / look), no move in flight, not lifted (imu), and ≥ RATE_S since
    the last turn
  * |delta| ≥ MIN_DELTA_DEG (don't twitch)
Then one goto: head yaw toward the sound (≤ HEAD_MAX_DEG from centre); if the sound is further round, the body
carries the rest (body_yaw). After the turn the face tracker resumes (look() holds tracking for the move only).

Sign calibration: the sign is EMPIRICAL (REACHY_DOA_SIGN, default +1 = +yaw is the robot's left, the SDK
convention). Whenever speech and a tracked face coincide we count whether the DoA side agrees with the face's x
(x<0 = face on the left of the image) → status().calib {agree, disagree, suggested_sign}. The owner confirms by
speaking from TINY's left once.

Frames: REACHY_DOA_FRAME=head (default — mics move with the head, delta is added to the current head yaw) or
body (delta is a body-frame absolute yaw).
"""
from __future__ import annotations

import logging
import math
import os
import threading
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, Optional

log = logging.getLogger("reachy.dash.doa")

ENABLED_DEFAULT = os.getenv("REACHY_DOA_TURN", "1") == "1"
SIGN = 1.0 if os.getenv("REACHY_DOA_SIGN", "1").strip() not in ("-1", "-") else -1.0
FRAME = os.getenv("REACHY_DOA_FRAME", "head").lower()
MIN_CONSEC = int(os.getenv("REACHY_DOA_MIN_CONSEC", "6"))
TOL_DEG = float(os.getenv("REACHY_DOA_TOL_DEG", "12"))
RATE_S = float(os.getenv("REACHY_DOA_RATE_S", "3"))
MIN_DELTA_DEG = float(os.getenv("REACHY_DOA_MIN_DELTA_DEG", "10"))
HEAD_MAX_DEG = float(os.getenv("REACHY_DOA_HEAD_MAX_DEG", "45"))
BODY_MAX_DEG = float(os.getenv("REACHY_DOA_BODY_MAX_DEG", "60"))      # DoA alone never swings the body past this
RAIL_DEG = float(os.getenv("REACHY_DOA_RAIL_DEG", "3"))               # 0 / π are the array's rails → not a bearing
SPEAK_TAIL_S = float(os.getenv("REACHY_DOA_SPEAK_TAIL_S", "1.5"))     # TINY's own voice + room echo
WINDUP_S = float(os.getenv("REACHY_DOA_WINDUP_S", "10"))              # same-direction turn within this window …
WINDUP_RATIO = float(os.getenv("REACHY_DOA_WINDUP_RATIO", "0.6"))     # … while the bearing did not shrink → suspect
FACE_FRESH_S = float(os.getenv("REACHY_DOA_FACE_FRESH_S", "1.5"))
TURN_S = float(os.getenv("REACHY_DOA_TURN_DURATION_S", "0.7"))
STALE_S = 1.0                      # a frame gap longer than this breaks the streak


class Turner:
    """Feed it state frames (on_frame); it decides when to turn and calls `look(yaw=, body_yaw=, pitch=, ...)`."""

    def __init__(self, look: Callable[..., Any], tracker: Any = None, moves_running: Optional[Callable[[], int]] = None,
                 now_playing: Optional[Callable[[], bool]] = None, lifted: Optional[Callable[[], bool]] = None,
                 on_change: Optional[Callable[[Dict[str, Any]], None]] = None, sign: float = SIGN,
                 enabled: bool = ENABLED_DEFAULT) -> None:
        self._look = look
        self._tracker = tracker
        self._moves_running = moves_running or (lambda: 0)
        self._now_playing = now_playing or (lambda: False)
        self._lifted = lifted or (lambda: False)
        self._on_change = on_change
        self._lock = threading.Lock()
        self.enabled = bool(enabled)
        self.sign = 1.0 if sign >= 0 else -1.0
        self.frame = FRAME
        self._streak: Deque[float] = deque(maxlen=max(MIN_CONSEC, 8))
        self._last_frame_t = 0.0
        self.last_angle: Optional[float] = None
        self.speech = False
        self.turns = 0
        self.last_turn_t: Optional[float] = None
        self.last_turn: Optional[Dict[str, Any]] = None
        self.why: Optional[str] = None
        self.error: Optional[str] = None
        self.agree = 0
        self.disagree = 0
        self.windups = 0
        self._quiet_since = 0.0
        self._last_emit: Optional[tuple] = None

    def _own_voice(self) -> bool:
        tr = self._tracker
        fn = getattr(tr, "is_speaking", None)
        try:
            return bool(fn(SPEAK_TAIL_S)) if callable(fn) else False
        except Exception:  # noqa: BLE001
            return False

    # ── public ──
    def set_enabled(self, on: bool, who: str = "dashboard") -> Dict[str, Any]:
        with self._lock:
            self.enabled = bool(on)
            self._streak.clear()
            self.why = None if on else "disabled"
        log.info("doa turn %s by %s", "ON" if on else "OFF", who)
        st = self.status()
        self._emit(st, force=True)
        return st

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {"enabled": self.enabled, "armed": len(self._streak) >= MIN_CONSEC and self._agree(),
                    "speech": self.speech, "angle_deg": None if self.last_angle is None else round(math.degrees(self.last_angle), 1),
                    "delta_deg": None if self.last_angle is None else round(self._delta_deg(self.last_angle), 1),
                    "turns": self.turns, "windups": self.windups, "last_turn_t": self.last_turn_t, "last_turn": self.last_turn, "why": self.why,
                    "error": self.error, "sign": self.sign, "frame": self.frame,
                    "rules": {"min_consec": MIN_CONSEC, "tol_deg": TOL_DEG, "rate_s": RATE_S, "min_delta_deg": MIN_DELTA_DEG,
                              "head_max_deg": HEAD_MAX_DEG, "body_max_deg": BODY_MAX_DEG, "rail_deg": RAIL_DEG,
                              "speak_tail_s": SPEAK_TAIL_S, "windup_s": WINDUP_S},
                    "calib": {"agree": self.agree, "disagree": self.disagree,
                              "suggested_sign": self._suggested_sign()}}

    # ── the frame hook (called from the stream thread at ≤ 10 Hz) ──
    def on_frame(self, frame: Dict[str, Any]) -> None:
        d = frame.get("doa") if isinstance(frame, dict) else None
        if not isinstance(d, dict) or not isinstance(d.get("angle"), (int, float)):
            return
        now = time.monotonic()
        angle = float(d["angle"])
        speech = bool(d.get("speech_detected"))
        with self._lock:
            self.last_angle, self.speech = angle, speech
            if now - self._last_frame_t > STALE_S:
                self._streak.clear()
            self._last_frame_t = now
            if not speech:
                self._streak.clear()
                self._quiet_since = self._quiet_since or now
                self._set_why("no speech")
                self._emit_locked()
                return
            self._quiet_since = 0.0
            deg = math.degrees(angle)
            if deg <= RAIL_DEG or deg >= 180.0 - RAIL_DEG:
                # 0 / π are the rails of a linear array (seen as the daemon's value for TINY's own speaker and for
                # "no estimate") — never a bearing to turn to, and they break the streak.
                self._streak.clear()
                self._set_why("rail reading")
                self._emit_locked()
                return
            if self._own_voice():
                self._streak.clear()
                self._set_why("TINY is speaking")
                self._emit_locked()
                return
            self._streak.append(angle)
            self._calibrate_locked(angle)
            if not self.enabled:
                self._set_why("disabled")
                self._emit_locked()
                return
            reason = self._blocked_locked(now)
            if reason:
                self._set_why(reason)
                self._emit_locked()
                return
            mean = sum(self._streak) / len(self._streak)
            delta = self._delta_deg(mean)
            if abs(delta) < MIN_DELTA_DEG:
                self._set_why(f"already facing ({delta:+.0f}°)")
                self._emit_locked()
                return
            lt = self.last_turn
            if lt and time.time() - (lt.get("t") or 0) < WINDUP_S and (lt.get("delta_deg", 0) * delta) > 0 \
                    and abs(delta) >= WINDUP_RATIO * abs(lt.get("delta_deg", 0)):
                # We just turned this way and the bearing did not shrink: the sound moves with us (own speaker,
                # base-mounted array, echo) — do not wind the body up. Needs a quiet gap before trying again.
                self.windups += 1
                self._streak.clear()
                self._set_why("windup guard")
                self._emit_locked()
                return
            plan = self._plan(frame, delta)
            self.last_turn_t = time.time()
            self.turns += 1
            self._streak.clear()
            self.why = None
            self.last_turn = {"t": self.last_turn_t, "angle_deg": round(math.degrees(mean), 1), "delta_deg": round(delta, 1), **plan}
        # motors outside the lock
        try:
            self._look(yaw=plan["yaw"], body_yaw=plan["body_yaw"], pitch=plan["pitch"], roll=0.0,
                       duration=TURN_S, who="doa")
            self.error = None
            log.info("doa: turned toward %.0f° (delta %+.0f° → head %.0f°, body %s)", math.degrees(mean), delta,
                     plan["yaw"], plan["body_yaw"])
        except Exception as e:  # noqa: BLE001
            self.error = str(e)[:200]
            log.warning("doa turn failed: %s", self.error)
        self._emit(self.status(), force=True)

    # ── internals (lock held) ──
    def _delta_deg(self, angle: float) -> float:
        return self.sign * math.degrees(math.pi / 2 - angle)

    def _agree(self) -> bool:
        if len(self._streak) < MIN_CONSEC:
            return False
        tail = list(self._streak)[-MIN_CONSEC:]
        m = sum(tail) / len(tail)
        return all(abs(math.degrees(a - m)) <= TOL_DEG for a in tail)

    def _blocked_locked(self, now: float) -> Optional[str]:
        if len(self._streak) < MIN_CONSEC:
            return f"listening {len(self._streak)}/{MIN_CONSEC}"
        if not self._agree():
            return "sound is moving"
        tr = self._tracker
        if tr is not None and getattr(tr, "enabled", False):
            face = getattr(tr, "face", {}) or {}
            seen = getattr(tr, "face_seen_at", 0.0) or 0.0
            if face.get("detected") and time.time() - seen <= FACE_FRESH_S:
                return "face tracker has a lock"
            try:
                holds = tr._live_holds()  # noqa: SLF001 — same package
            except Exception:  # noqa: BLE001
                holds = {}
            if holds:
                return "tracker hold: " + ",".join(sorted(holds))
        if self._lifted():
            return "lifted"
        if self._now_playing() or self._moves_running() > 0:
            return "move in flight"
        if self.last_turn_t and time.time() - self.last_turn_t < RATE_S:
            return "rate limit"
        return None

    def _plan(self, frame: Dict[str, Any], delta: float) -> Dict[str, Any]:
        hp = frame.get("head_pose") or {}
        cur_yaw = math.degrees(float(hp.get("yaw", 0.0) or 0.0))
        cur_pitch = math.degrees(float(hp.get("pitch", 0.0) or 0.0))
        cur_body = math.degrees(float(frame.get("body_yaw") or 0.0))
        target = (cur_yaw + delta) if self.frame == "head" else delta
        head = max(-HEAD_MAX_DEG, min(HEAD_MAX_DEG, target))
        rest = target - head
        body: Optional[float] = None
        if abs(rest) > 1.0:
            body = max(-BODY_MAX_DEG, min(BODY_MAX_DEG, cur_body + rest))
        return {"yaw": round(head, 1), "body_yaw": None if body is None else round(body, 1),
                "pitch": round(max(-20.0, min(15.0, cur_pitch)), 1), "from_yaw": round(cur_yaw, 1)}

    def _calibrate_locked(self, angle: float) -> None:
        tr = self._tracker
        if tr is None or not getattr(tr, "enabled", False):
            return
        face = getattr(tr, "face", {}) or {}
        x = face.get("x")
        if not face.get("detected") or not isinstance(x, (int, float)) or abs(x) < 0.15:
            return
        raw = math.pi / 2 - angle                       # +: sound on the LEFT (Pollen: 0 = left)
        if abs(math.degrees(raw)) < MIN_DELTA_DEG or self._own_voice():
            return
        # face x<0 = left of the image = robot's left. Agreement means SIGN=+1 is right.
        if (raw > 0) == (x < 0):
            self.agree += 1
        else:
            self.disagree += 1

    def _suggested_sign(self) -> Optional[float]:
        n = self.agree + self.disagree
        if n < 10:
            return None
        return 1.0 if self.agree >= self.disagree else -1.0

    def _set_why(self, why: str) -> None:
        self.why = why

    def _emit_locked(self) -> None:
        key = (self.enabled, self.speech, None if self.last_angle is None else round(self.last_angle, 1), self.why, self.turns)
        if key != self._last_emit:
            self._last_emit = key
            st = self.status_nolock()
            if self._on_change:
                try:
                    self._on_change({"type": "doa", **st})
                except Exception as e:  # noqa: BLE001
                    log.debug("doa emit: %s", e)

    def status_nolock(self) -> Dict[str, Any]:
        return {"enabled": self.enabled, "armed": len(self._streak) >= MIN_CONSEC and self._agree(), "speech": self.speech,
                "angle_deg": None if self.last_angle is None else round(math.degrees(self.last_angle), 1),
                "delta_deg": None if self.last_angle is None else round(self._delta_deg(self.last_angle), 1),
                "turns": self.turns, "last_turn_t": self.last_turn_t, "why": self.why, "sign": self.sign}

    def _emit(self, st: Dict[str, Any], force: bool = False) -> None:
        if self._on_change and force:
            try:
                self._on_change({"type": "doa", **st})
            except Exception as e:  # noqa: BLE001
                log.debug("doa emit: %s", e)
