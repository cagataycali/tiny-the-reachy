"""The landing's emotion swatch is backed by real frames: every move button names a sequence dir with exactly that many frames,
a poses json produced from the same move, and the three sequences together stay under the 1.2 MB budget."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "docs/overrides/home.html"
LANDING = ROOT / "docs/assets/landing"


def _buttons():
    html = HTML.read_text()
    block = html.split('class="l-swatch"', 1)[1].split("</div>", 1)[0]
    return re.findall(r'data-pick="([a-z0-9]+)" data-frames="(\d+)" data-seq="\{\{ \'assets/landing/seq/([a-z0-9]+)/\' \| url \}\}"'
                      r' data-poses="\{\{ \'assets/landing/poses/([a-z0-9]+)\.json\' \| url \}\}" data-still="\{\{ \'(assets/landing/seq/[a-z0-9]+/\d\d\.webp)\' \| url \}\}"', block)


def test_swatch_moves_have_their_frames_poses_and_still():
    buttons = _buttons()
    assert len(buttons) == 2, buttons
    for name, n, seq, poses, still in buttons:
        assert seq == poses == name
        frames = sorted((LANDING / "seq" / name).glob("*.webp"))
        assert [f.name for f in frames] == [f"{k:02d}.webp" for k in range(int(n))], name
        j = json.loads((LANDING / "poses" / f"{name}.json").read_text())
        assert j["move"] == name and len(j["frames"]) == len(j["t"]) >= int(n)
        assert (ROOT / "docs" / still).exists(), still
        # the notes under the move are its own timestamps: data-at = t / duration, and t must be inside the move
        panel = HTML.read_text().split(f'<div class="l-move" data-move="{name}"', 1)[1].split("</ol>", 1)[0]
        for at, t in re.findall(r'data-at="([\d.]+)"><b>([\d.]+) s</b>', panel):
            assert abs(float(at) - float(t) / j["duration"]) < 0.03, (name, at, t)
            assert float(t) <= j["duration"] + 0.05


def test_sequences_stay_under_the_frame_budget():
    total = sum(f.stat().st_size for d in ("curious1", "fear1", "hero") for f in (LANDING / "seq" / d).glob("*.webp"))
    assert total < 1_200_000, total


def test_hero_motor_vector_is_the_daemon_command_per_frame():
    """The hero's hover readout shows poses.motors — 9 values per sampled frame (yaw_body, stewart_1..6, antennas), one per frame."""
    import json
    for name in ("curious1", "fear1"):
        d = json.loads((ROOT / "docs/assets/landing/poses" / f"{name}.json").read_text())
        assert d["motor_names"] == ["yaw_body", "stewart_1", "stewart_2", "stewart_3", "stewart_4", "stewart_5", "stewart_6", "right_antenna", "left_antenna"]
        assert len(d["motors"]) == len(d["frames"]) and all(len(m) == 9 for m in d["motors"])
        # antennas in the motor row are the recorded antennas (ctrl sign undone), not a second source
        assert all(abs(m[7] - a[0]) < 0.11 and abs(m[8] - a[1]) < 0.11 for m, a in zip(d["motors"], d["antennas"]))
    html = (ROOT / "docs/overrides/home.html").read_text()
    assert len(re.findall(r'data-hm="\d"', html)) == 9
