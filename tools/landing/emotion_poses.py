"""emotion_poses.py — precompute the twin's body poses for a REAL recorded emotion (landing page chapter data).

Ground truth, nothing invented:
  * the model   = dashboard/frontend/public/model/twin.xml — the exact file the cockpit twin loads (MuJoCo 3.13.0, same as the
                  WASM build the dashboard runs; see dashboard/frontend/src/lib/mujoco.ts)
  * the move    = pollen-robotics/reachy-mini-emotions-library/<name>.json from the local HF cache — the file the robot plays
                  when reachy_express('<name>') runs (tools/reachy_expression.py → RecordedMoves)
  * the IK      = reachy_mini_rust_kinematics + kinematics_data.json from the reachy_mini 1.10.0 wheel — the daemon's own
                  AnalyticalKinematics (reachy_mini/kinematics/analytical_kinematics.py), head 4x4 → body_yaw + stewart_1..6
  * antennas    = the daemon's MuJoCo backend convention: ctrl = -antenna (reachy_mini/daemon/backend/mujoco/backend.py)

Output: docs/assets/landing/poses/<name>.json
  {"move": name, "description": <the json's own description>, "duration": s, "bodies": [17 names],
   "frames": [[x,y,z,qw,qx,qy,qz] * bodies] * N, "t": [s] * N, "head": [{"roll","pitch","yaw","z"}] * N (deg / mm),
   "antennas": [[right,left] deg] * N, "body_yaw": [deg] * N, "ranges": {...}}
Also `--index` writes docs/js/landing/emotions.json = [{name, description, duration, samples}] for all moves in the cache.

Run (lane venv):  ~/.tiny/reachy-landing-20260921/.venv/bin/python tools/landing/emotion_poses.py curious1 --fps 12
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MODEL_XML = ROOT / "dashboard" / "frontend" / "public" / "model" / "twin.xml"
OUT_DIR = ROOT / "docs" / "assets" / "landing" / "poses"
INDEX_OUT = ROOT / "docs" / "js" / "landing" / "emotions.json"
HF_GLOB = os.path.expanduser("~/.cache/huggingface/hub/datasets--pollen-robotics--reachy-mini-emotions-library/snapshots/*/")
KIN_DATA = Path(os.environ.get("KINEMATICS_DATA", os.path.expanduser("~/.tiny/reachy-landing-20260921/kinematics_data.json")))
MOTOR_JOINTS = ["yaw_body", "stewart_1", "stewart_2", "stewart_3", "stewart_4", "stewart_5", "stewart_6", "right_antenna", "left_antenna"]


def snapshot_dir(want_wav: bool = True) -> Path:
    """The HF snapshot that carries the 81 moves WITH their .wav (the one RecordedMoves plays)."""
    best = None
    for d in sorted(glob.glob(HF_GLOB)):
        n_json = len(glob.glob(d + "*.json")); n_wav = len(glob.glob(d + "*.wav"))
        if n_json and (not want_wav or n_wav):
            best = (n_json, d) if best is None or n_json > best[0] else best
    if not best:
        sys.exit("emotions library not in the HF cache")
    return Path(best[1])


def euler_deg(m) -> tuple[float, float, float]:
    """roll, pitch, yaw (deg) of a 3x3/4x4 matrix — same formula as ReachySim.headEuler() in lib/mujoco.ts."""
    yaw = math.atan2(m[1][0], m[0][0]); pitch = math.atan2(-m[2][0], math.hypot(m[2][1], m[2][2])); roll = math.atan2(m[2][1], m[2][2])
    return math.degrees(roll), math.degrees(pitch), math.degrees(yaw)


class DaemonIK:
    """AnalyticalKinematics without importing reachy_mini (its deps need the robot); logic copied 1:1."""

    def __init__(self, data_path: Path):
        from reachy_mini_rust_kinematics import ReachyMiniRustKinematics
        data = json.load(open(data_path, "rb"))
        self.head_z_offset = data["head_z_offset"]
        self.kin = ReachyMiniRustKinematics(data["motor_arm_length"], data["rod_length"])
        for motor in data["motors"]:
            self.kin.add_branch(motor["branch_position"], np.linalg.inv(motor["T_motor_world"]).tolist(), 1 if motor["solution"] else -1)
        sleep = np.array([[0.911, 0.004, 0.413, -0.021], [-0.004, 1.0, -0.001, 0.001], [-0.413, -0.001, 0.911, -0.044], [0, 0, 0, 1.0]])
        sleep[2, 3] += self.head_z_offset
        self.kin.reset_forward_kinematics(sleep.tolist())

    def ik(self, pose, body_yaw: float) -> list[float]:
        p = np.array(pose, dtype=float).copy(); p[2, 3] += self.head_z_offset
        return list(self.kin.inverse_kinematics_safe(p.tolist(), body_yaw=body_yaw, max_relative_yaw=math.radians(65), max_body_yaw=math.radians(160)))


def load_move(name: str) -> dict:
    p = snapshot_dir() / f"{name}.json"
    if not p.exists():
        sys.exit(f"no such move: {p}")
    return json.load(open(p))


def compute(name: str, fps: float, settle_s: float = 0.6) -> dict:
    import mujoco

    move = load_move(name)
    t = np.array(move["time"], dtype=float); traj = move["set_target_data"]
    ik = DaemonIK(KIN_DATA)
    model = mujoco.MjModel.from_xml_path(str(MODEL_XML)); data = mujoco.MjData(model)
    act = {mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, i): i for i in range(model.nu)}
    slot = [act[j] for j in MOTOR_JOINTS]
    bodies = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, b) for b in range(1, model.nbody)]  # skip world
    head_site = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "head")

    def targets(i: int) -> list[float]:
        s = traj[i]
        j7 = ik.ik(s["head"], float(s["body_yaw"]))
        r, l = s["antennas"]
        return j7 + [-float(r), -float(l)]     # daemon mujoco backend: ctrl[-2:] = -antennas

    def set_ctrl(vals):
        for k, i in enumerate(slot):
            data.ctrl[i] = vals[k]

    # settle like ReachySim.settle(): ramp from rest to the first pose over 60 % of 300 steps (closed chain lands on the right branch)
    mujoco.mj_resetData(model, data)
    first = targets(0)
    for k in range(1, 301):
        a = min(1.0, k / 180.0); set_ctrl([v * a for v in first]); mujoco.mj_step(model, data)

    h = model.opt.timestep
    sample_t = np.arange(0.0, t[-1] + 1e-9, 1.0 / fps)
    frames, heads, ants, byaw, tt = [], [], [], [], []
    sim_t = 0.0; ti = 0
    for st in sample_t:
        # advance the sim to st, updating ctrl from the recorded trajectory as time passes (100 Hz recording)
        while sim_t < st:
            while ti + 1 < len(t) and t[ti + 1] <= sim_t:
                ti += 1
            set_ctrl(targets(ti)); mujoco.mj_step(model, data); sim_t += h
        row = []
        for b in range(1, model.nbody):
            p = data.xpos[b]; q = data.xquat[b]
            row += [round(float(p[0]), 5), round(float(p[1]), 5), round(float(p[2]), 5), round(float(q[0]), 5), round(float(q[1]), 5), round(float(q[2]), 5), round(float(q[3]), 5)]
        frames.append(row)
        m = data.site_xmat[head_site].reshape(3, 3); r, pch, y = euler_deg(m)
        heads.append({"roll": round(r, 1), "pitch": round(pch, 1), "yaw": round(y, 1), "z": round(float(data.site_xpos[head_site][2]) * 1000, 1)})
        s = traj[min(ti, len(traj) - 1)]
        ants.append([round(math.degrees(s["antennas"][0]), 1), round(math.degrees(s["antennas"][1]), 1)])
        byaw.append(round(math.degrees(s["body_yaw"]), 1)); tt.append(round(float(st), 3))

    def rng(xs): return [round(min(xs), 1), round(max(xs), 1)]
    ranges = {"head_yaw": rng([x["yaw"] for x in heads]), "head_pitch": rng([x["pitch"] for x in heads]), "head_roll": rng([x["roll"] for x in heads]),
              "antenna_right": rng([a[0] for a in ants]), "antenna_left": rng([a[1] for a in ants]), "body_yaw": rng(byaw)}
    return {"move": name, "source": "pollen-robotics/reachy-mini-emotions-library", "snapshot": snapshot_dir().name[:8],
            "description": move["description"], "duration": round(float(t[-1]), 2), "samples": len(t), "fps": fps,
            "model": MODEL_XML.relative_to(ROOT).as_posix(), "mujoco": mujoco.__version__, "bodies": bodies, "t": tt,
            "frames": frames, "head": heads, "antennas": ants, "body_yaw": byaw, "ranges": ranges}


def write_index() -> int:
    rows = []
    for p in sorted(snapshot_dir().glob("*.json")):
        d = json.load(open(p)); t = d["time"]
        rows.append({"name": p.stem, "description": d["description"], "duration": round(float(t[-1]), 1), "samples": len(t), "sound": (p.with_suffix(".wav")).exists()})
    INDEX_OUT.parent.mkdir(parents=True, exist_ok=True)
    INDEX_OUT.write_text(json.dumps({"source": "pollen-robotics/reachy-mini-emotions-library", "snapshot": snapshot_dir().name[:8], "moves": rows}, ensure_ascii=False, indent=0) + "\n")
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("moves", nargs="*"); ap.add_argument("--fps", type=float, default=12); ap.add_argument("--index", action="store_true")
    a = ap.parse_args()
    if a.index:
        print("index:", write_index(), "moves →", INDEX_OUT.relative_to(ROOT))
    for name in a.moves:
        d = compute(name, a.fps)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out = OUT_DIR / f"{name}.json"
        out.write_text(json.dumps(d, separators=(",", ":")) + "\n")
        print(f"{name}: {len(d['frames'])} frames @ {a.fps} fps, {d['duration']} s, {out.stat().st_size // 1024} KB → {out.relative_to(ROOT)}")
        print("  ranges:", d["ranges"])


if __name__ == "__main__":
    main()
