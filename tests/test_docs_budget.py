"""The docs word budget is a CI gate (owner directive 2026-09-21: cut 60 %, keep the soul). tools/docs_budget.py holds the numbers."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import docs_budget as b  # noqa: E402


def test_budget_passes():
    rows, problems, _notes = b.audit()
    assert not problems, "\n".join(problems)


def test_ratchet_is_gone():
    """The ratchet reached the target at it12: ceiling == target == 6,400 (40 % of the 16,007 measured at 7f46bc4)."""
    assert b.SITE_CEILING == b.SITE_TARGET == 6400
    total = sum(r["words"] for r in b.audit()[0])
    assert total <= b.SITE_CEILING


def test_grace_pages_exist_and_are_needed():
    """A page in GRACE must exist and must still be over budget or missing its box — otherwise remove it from GRACE."""
    for rel in b.GRACE:
        p = b.DOCS / rel
        assert p.exists(), rel
        md = p.read_text(encoding="utf-8")
        assert b.count_words(md) > b.limit_for(rel) or not b.has_tldr(md), f"{rel}: within budget — drop it from GRACE"


def test_counting_rules():
    md = "---\ntitle: x\n---\n# H\n\nthree words here\n\n```py\nnot counted at all\n```\n\n<span>tag</span> | a | b |\n"
    assert b.count_words(md) == 3 + 1 + 1 + 1 + 1  # H, three, words, here, tag, a, b


@pytest.mark.parametrize("rel", ["reference/env.md", "reference/api.md"])
def test_table_pages_have_no_prose(rel):
    """env/api are tables: every visible line outside the abstract box is a table row, heading, marker or blank."""
    md = (b.DOCS / rel).read_text(encoding="utf-8")
    body = b.visible_text(md)
    in_box = False
    for ln in body.splitlines():
        s = ln.strip()
        if s.startswith("!!! "):
            in_box = True
            continue
        if in_box and (ln.startswith("    ") or not s):
            continue
        in_box = False
        assert not s or s.startswith(("|", "#", "<!--", "_", "COCKPIT", "curl")) or s.endswith(("markdown>", "</div>")), f"{rel}: prose line: {s[:80]}"


def test_env_purposes_are_short():
    sys.path.insert(0, str(ROOT / "scripts"))
    import envdoc_notes  # noqa: E402
    W = b._WORD
    long = {k: len(W.findall(v)) for k, v in envdoc_notes.NOTES.items() if len(W.findall(v)) > 12}
    assert not long, long


def test_cli_exit_code():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "docs_budget.py")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:]
