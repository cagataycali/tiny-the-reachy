"""dashboard/doa.py — turn toward the speaker, from DoA frames riding the daemon state stream."""
from __future__ import annotations

import math
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("REACHY_NO_AUTOAPP", "1")

from dashboard import doa  # noqa: E402


class FakeTracker:
    def __init__(self):
        self.enabled = False
        self.face = {"detected": False, "x": None}
        self.face_seen_at = 0.0
        self.holds = {}

    def _live_holds(self):
        return self.holds

    def is_speaking(self, tail=0.0):
        return False


def frame(angle_deg, speech=True, yaw_deg=0.0, body_deg=0.0):
    return {"doa": {"angle": math.radians(angle_deg), "speech_detected": speech},
            "head_pose": {"yaw": math.radians(yaw_deg), "pitch": 0.0}, "body_yaw": math.radians(body_deg)}


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr(doa, "MIN_CONSEC", 5)
    monkeypatch.setattr(doa, "RATE_S", 2.0)
    monkeypatch.setattr(doa, "TOL_DEG", 10.0)
    monkeypatch.setattr(doa, "MIN_DELTA_DEG", 8.0)
    monkeypatch.setattr(doa, "BODY_MAX_DEG", 60.0)
    looks = []
    tr = FakeTracker()
    t = doa.Turner(look=lambda **kw: looks.append(kw), tracker=tr, enabled=True, sign=1.0)
    return t, tr, looks


def test_turns_after_five_agreeing_speech_frames(rig):
    t, _, looks = rig
    for _ in range(4):
        t.on_frame(frame(30))          # sound 60° to the LEFT (Pollen: 0 = left, 90 = front)
    assert looks == [] and t.status()["why"].startswith("listening 4/5")
    t.on_frame(frame(30))
    assert len(looks) == 1
    assert looks[0]["yaw"] == 45.0 and looks[0]["body_yaw"] == 15.0   # 60° → head 45 + body 15
    assert looks[0]["who"] == "doa" and t.status()["turns"] == 1


def test_sign_flips_direction(monkeypatch):
    looks = []
    t = doa.Turner(look=lambda **kw: looks.append(kw), enabled=True, sign=-1.0)
    monkeypatch.setattr(doa, "MIN_CONSEC", 5)
    monkeypatch.setattr(doa, "MIN_DELTA_DEG", 8.0)
    for _ in range(5):
        t.on_frame(frame(60))          # 30° left → with sign −1 the head goes right
    assert looks and looks[0]["yaw"] == -30.0 and looks[0]["body_yaw"] is None


def test_no_speech_breaks_the_streak(rig):
    t, _, looks = rig
    for _ in range(4):
        t.on_frame(frame(30))
    t.on_frame(frame(30, speech=False))
    t.on_frame(frame(30))
    assert looks == [] and t.status()["why"].startswith("listening 1/5")


def test_moving_sound_does_not_turn(rig):
    t, _, looks = rig
    for a in (20, 45, 70, 95, 120):
        t.on_frame(frame(a))
    assert looks == [] and t.status()["why"] == "sound is moving"


def test_face_lock_wins(rig):
    t, tr, looks = rig
    tr.enabled = True
    tr.face = {"detected": True, "x": -0.4}
    tr.face_seen_at = time.time()
    for _ in range(5):
        t.on_frame(frame(30))
    assert looks == [] and t.status()["why"] == "face tracker has a lock"
    assert t.status()["calib"]["agree"] == 5 and t.status()["calib"]["disagree"] == 0   # left sound, left face


def test_tracker_hold_and_rate_limit(rig):
    t, tr, looks = rig
    tr.enabled = True
    tr.holds = {"speaking": time.monotonic() + 5}
    for _ in range(5):
        t.on_frame(frame(30))
    assert looks == [] and t.status()["why"].startswith("tracker hold")
    tr.holds = {}
    for _ in range(5):
        t.on_frame(frame(30))
    assert len(looks) == 1
    for _ in range(5):
        t.on_frame(frame(150))         # new sound on the right, but within RATE_S
    assert len(looks) == 1 and t.status()["why"] == "rate limit"


def test_already_facing_and_disabled(rig):
    t, _, looks = rig
    for _ in range(5):
        t.on_frame(frame(93))          # 3° off → no twitch
    assert looks == [] and t.status()["why"].startswith("already facing")
    t.set_enabled(False)
    for _ in range(6):
        t.on_frame(frame(30))
    assert looks == [] and t.status()["why"] == "disabled"


def test_head_frame_adds_current_yaw(rig):
    t, _, looks = rig
    for _ in range(5):
        t.on_frame(frame(60, yaw_deg=-20))   # 30° left of the head, head already at −20 → target +10 absolute
    assert looks and looks[0]["yaw"] == 10.0 and looks[0]["body_yaw"] is None


def test_calibration_suggests_flip_when_face_disagrees(rig):
    t, tr, _ = rig
    tr.enabled = True
    tr.face = {"detected": True, "x": 0.5}     # face on the RIGHT of the image
    tr.face_seen_at = time.time()
    for _ in range(12):
        t.on_frame(frame(30))                  # but sound says LEFT
    c = t.status()["calib"]
    assert c["disagree"] == 12 and c["suggested_sign"] == -1.0


def test_rail_readings_and_own_voice_never_turn(rig, monkeypatch):
    t, tr, looks = rig
    for _ in range(6):
        t.on_frame(frame(180.0))                       # π rail = TINY's own speaker / no estimate
    assert looks == [] and t.status()["why"] == "rail reading"
    for _ in range(6):
        t.on_frame(frame(0.0))
    assert looks == [] and t.status()["why"] == "rail reading"
    tr.is_speaking = lambda tail=0.0: True             # 'speaking' hold live (even with no face lock)
    for _ in range(6):
        t.on_frame(frame(30))
    assert looks == [] and t.status()["why"] == "TINY is speaking"
    assert t.status()["calib"] == {"agree": 0, "disagree": 0, "suggested_sign": None}


def test_windup_guard(rig, monkeypatch):
    """After turning left toward a sound, the same bearing again (it moved with us) must not turn us further."""
    monkeypatch.setattr(doa, "RATE_S", 0.0)
    t, _, looks = rig
    for _ in range(5):
        t.on_frame(frame(30))                          # 60° left → turn
    assert len(looks) == 1
    for _ in range(5):
        t.on_frame(frame(30, yaw_deg=45))              # still 60° left of the (now turned) head → suspicious
    assert len(looks) == 1 and t.status()["why"] == "windup guard" and t.status()["windups"] == 1
    for _ in range(5):
        t.on_frame(frame(150, yaw_deg=45))             # a genuinely different bearing (right) is fine
    assert len(looks) == 2


def test_body_travel_is_capped(rig):
    t, _, looks = rig
    for _ in range(5):
        t.on_frame(frame(5, yaw_deg=0, body_deg=50))   # 85° left, body already at 50 → head 45, body capped 60
    assert looks and looks[0]["yaw"] == 45.0 and looks[0]["body_yaw"] == 60.0
