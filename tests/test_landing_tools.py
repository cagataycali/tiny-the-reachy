"""The landing's tool wall (docs/overrides/home.html §5) must list exactly the tools the generated reference lists."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _wall_tools() -> set[str]:
    html = (ROOT / "docs/overrides/home.html").read_text()
    wall = html.split('class="l-toolwall"', 1)[1].split("</ul>", 1)[0]
    return set(re.findall(r"<code>([a-z_]+)</code>", wall)) - {"TINY_MCP"}


def _reference_tools() -> set[str]:
    md = (ROOT / "docs/reference/tools/index.md").read_text()
    rows = [l for l in md.splitlines() if l.startswith("| [")]
    names: set[str] = set()
    for row in rows:
        names |= set(re.findall(r"`([a-z_]+)`", row.split("|")[2]))
    return names


def test_wall_matches_reference():
    assert _wall_tools() == _reference_tools()


def test_wall_count_matches_kicker():
    html = (ROOT / "docs/overrides/home.html").read_text()
    n = int(re.search(r'<p class="l-kicker">(\d+) tools · (\d+) modules', html).group(1))
    assert n == len(_reference_tools()) == 28
