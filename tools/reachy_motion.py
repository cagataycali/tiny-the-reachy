"""TINY motion tools — head (6-DOF Stewart platform), body yaw, antennas.

Reachy Mini has NO arms/legs. Expression is through:
  - head pose: x,y,z (mm) + roll,pitch,yaw (deg)
  - body_yaw: rotation around vertical axis
  - 2 antennas: [right, left] angles (deg) — also usable as buttons

goto_target() = smooth interpolated gestures (>=0.5s). Default.
set_target()  = real-time control loop (10Hz+), no interpolation.
"""
from typing import Optional, List
from strands import tool
from ._reachy_common import (
    get_mini, clamp, ok, err,
    LIM_HEAD_PITCH, LIM_HEAD_ROLL, LIM_HEAD_YAW, LIM_BODY_YAW,
)


def _hold_tracking(name: str, on: bool, ttl: float = 12.0) -> None:
    try:
        from .head_tracking import tracking_hold  # noqa: PLC0415
        tracking_hold(name, on, ttl)
    except Exception:  # noqa: BLE001 — never let tracking plumbing break a move
        pass


def _release_tracking_later(name: str, after: float) -> None:
    import threading  # noqa: PLC0415
    t = threading.Timer(after, _hold_tracking, args=(name, False))
    t.daemon = True
    t.start()


@tool
def reachy_look(
    x: float = 0.0, y: float = 0.0, z: float = 0.0,
    roll: float = 0.0, pitch: float = 0.0, yaw: float = 0.0,
    body_yaw: Optional[float] = 0.0,
    antennas: Optional[List[float]] = None,
    duration: float = 0.8,
    method: str = "minjerk",
) -> dict:
    """Move TINY's head to a pose (smooth interpolation). The primary gesture tool.

    Args:
        x, y, z: head translation in millimetres (small, ~[-20,20]).
        roll, pitch, yaw: head orientation in DEGREES.
            pitch/roll clamped to [-40,40], yaw to [-180,180].
        body_yaw: body rotation in DEGREES (clamped [-160,160]). None = keep current.
        antennas: optional [right_deg, left_deg] antenna angles.
        duration: seconds for the move (>=0.5 recommended for smoothness).
        method: "minjerk" (default) | "linear" | "ease_in_out" | "cartoon".

    Examples:
        reachy_look(pitch=15, yaw=20)              # look up-and-right
        reachy_look(roll=15, antennas=[30,-30])    # curious head-tilt + ears
        reachy_look(yaw=0, body_yaw=45)            # spin body, keep head level
    """
    import numpy as np
    from reachy_mini.utils import create_head_pose

    pitch = clamp(pitch, *LIM_HEAD_PITCH)
    roll = clamp(roll, *LIM_HEAD_ROLL)
    yaw = clamp(yaw, *LIM_HEAD_YAW)
    if body_yaw is not None:
        body_yaw = clamp(body_yaw, *LIM_BODY_YAW)

    try:
        mini = get_mini()
        head = create_head_pose(x=x, y=y, z=z, roll=roll, pitch=pitch, yaw=yaw,
                                degrees=True, mm=True)
        ant = None
        if antennas is not None:
            if len(antennas) != 2:
                return err("antennas must be [right_deg, left_deg]")
            ant = [np.deg2rad(antennas[0]), np.deg2rad(antennas[1])]
        body_rad = None if body_yaw is None else np.deg2rad(body_yaw)
        # an explicit look wins over daemon face tracking (1.10) for its duration + 2 s, then tracking resumes
        _hold_tracking("look", True, ttl=max(0.1, duration) + 3.0)
        mini.goto_target(head=head, antennas=ant, duration=max(0.1, duration),
                         method=method, body_yaw=body_rad)
        _release_tracking_later("look", 2.0)
        return ok(f"head→(r{roll:.0f} p{pitch:.0f} y{yaw:.0f}) "
                  f"body_yaw={body_yaw} antennas={antennas} in {duration}s")
    except Exception as e:
        return err(f"reachy_look failed: {e}")


@tool
def reachy_antennas(right: float = 0.0, left: float = 0.0, duration: float = 0.5) -> dict:
    """Move just the two antennas (TINY's 'ears'), in DEGREES. Great for emotion.

    right/left ~ [-90, 90] deg. Wiggle them for excitement, droop for sad.

    Examples:
        reachy_antennas(45, 45)     # both up — alert / happy
        reachy_antennas(-40, -40)   # both down — sad / sleepy
        reachy_antennas(60, -60)    # asymmetric — quizzical
    """
    import numpy as np
    try:
        mini = get_mini()
        mini.goto_target(antennas=[np.deg2rad(right), np.deg2rad(left)],
                         duration=max(0.1, duration), body_yaw=None)
        return ok(f"antennas → right={right}° left={left}°")
    except Exception as e:
        return err(f"reachy_antennas failed: {e}")


@tool
def reachy_body_turn(yaw: float = 0.0, duration: float = 1.0) -> dict:
    """Rotate TINY's body around the vertical axis, in DEGREES ([-160,160]).

    The head stays level (automatic_body_yaw keeps IK consistent). Use this
    to turn toward a speaker or scan the room.
    """
    import numpy as np
    yaw = clamp(yaw, *LIM_BODY_YAW)
    try:
        mini = get_mini()
        mini.goto_target(body_yaw=np.deg2rad(yaw), duration=max(0.1, duration))
        return ok(f"body turned to yaw={yaw}°")
    except Exception as e:
        return err(f"reachy_body_turn failed: {e}")


@tool
def reachy_home(duration: float = 1.0) -> dict:
    """Return TINY to the neutral/init pose (head centered, antennas rest)."""
    import numpy as np
    from reachy_mini.utils import create_head_pose
    try:
        mini = get_mini()
        mini.goto_target(head=create_head_pose(), antennas=[0.0, 0.0],
                         duration=duration, body_yaw=0.0)
        return ok("returned to home pose")
    except Exception as e:
        return err(f"reachy_home failed: {e}")


@tool
def reachy_wake(sleep: bool = False) -> dict:
    """Wake TINY up (init pose + wake emote + sound) or put it to sleep.

    Args:
        sleep: if True, run goto_sleep() instead of wake_up().
    """
    try:
        mini = get_mini()
        if sleep:
            mini.goto_sleep()
            return ok("TINY is now asleep 😴")
        mini.wake_up()
        return ok("TINY is awake ✨")
    except Exception as e:
        return err(f"reachy_wake failed: {e}")
