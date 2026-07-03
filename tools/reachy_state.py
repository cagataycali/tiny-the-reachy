"""TINY state tools — IMU, joint positions, current head pose. Read-only, safe."""
from strands import tool
from ._reachy_common import get_mini, ok, err


@tool
def reachy_get_state() -> dict:
    """Read TINY's live state: current head pose, joint positions, IMU (if present).

    IMU is only available on the Wireless (CM4) version — returns null on Lite.
    Cheap + safe; call before/after motion to verify.
    """
    try:
        mini = get_mini()
        head_pose = mini.get_current_head_pose()
        joints, antennas = mini.get_current_joint_positions()
        imu = None
        try:
            imu = mini.imu  # None on Lite
        except Exception:
            imu = None
        return ok(
            "state snapshot",
            head_pose=head_pose.tolist() if hasattr(head_pose, "tolist") else head_pose,
            joint_positions=list(joints) if joints is not None else None,
            antennas=list(antennas) if antennas is not None else None,
            imu=imu,
        )
    except Exception as e:
        return err(f"reachy_get_state failed: {e}")


@tool
def reachy_motors(mode: str = "enabled") -> dict:
    """Set TINY's motor torque mode.

    Args:
        mode: "enabled" (torque on, holds pose) |
              "disabled" (limp — safe to move by hand) |
              "gravity_compensation" (float / marionette mode).
    """
    try:
        mini = get_mini()
        m = mode.lower()
        if m == "enabled":
            mini.enable_motors()
        elif m == "disabled":
            mini.disable_motors()
        elif m in ("gravity_compensation", "gravity", "compliant"):
            mini.enable_gravity_compensation()
        else:
            return err(f"unknown mode '{mode}' — use enabled|disabled|gravity_compensation")
        return ok(f"motors → {m}")
    except Exception as e:
        return err(f"reachy_motors failed: {e}")
