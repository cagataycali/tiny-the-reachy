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
