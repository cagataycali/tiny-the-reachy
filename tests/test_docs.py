"""The docs are generated from the code — these tests keep the two from drifting.

Run: pytest tests/test_docs.py   (stdlib generators; no robot, no strands needed)
"""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import envdoc, routedoc, tooldoc  # noqa: E402

DOCS = ROOT / "docs"


def _all_docs_text() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in DOCS.rglob("*.md"))


def test_every_env_var_is_documented():
    names = set(envdoc.collect())
    assert names, "envdoc found nothing — scanner broken?"
    text = _all_docs_text()
    missing = sorted(n for n in names if f"`{n}`" not in text)
    assert not missing, f"env vars read by the code but absent from docs/: {missing}"


def test_every_env_var_has_a_purpose_note():
    from envdoc_notes import NOTES
    missing = sorted(n for n in envdoc.collect() if n not in NOTES)
    assert not missing, f"add a one-line purpose to scripts/envdoc_notes.py for: {missing}"


def test_tools_reference_is_fresh():
    pages = tooldoc.build()
    out = DOCS / "reference" / "tools"
    stale = [n for n, t in pages.items() if not (out / n).exists() or (out / n).read_text(encoding="utf-8") != t]
    assert not stale, f"run `python scripts/tooldoc.py` — stale: {stale}"


def test_every_tool_module_has_a_page():
    inv = tooldoc.inventory()
    undescribed = [m for m, v in inv.items() if "not yet described" in v["blurb"]]
    assert not undescribed, f"add these modules to scripts/tooldoc.MODULES: {undescribed}"
    total = sum(len(v["tools"]) for v in inv.values())
    assert total >= 26, total  # 21 robot tools + memory/prompts/dispatch/telegram/manage_* — never fewer


def test_every_dashboard_route_has_a_note():
    from routedoc_notes import NOTES
    rs = routedoc.routes()
    assert len(rs) >= 30, len(rs)
    missing = sorted(f"{r['method']} {r['path']}" for r in rs if not r["doc"])
    assert not missing, f"add to scripts/routedoc_notes.py: {missing}"


def test_generated_blocks_present():
    for page, name in (("reference/env.md", "env"), ("reference/api.md", "api")):
        text = (DOCS / page).read_text(encoding="utf-8")
        assert f"<!-- gen:{name} -->" in text and f"<!-- /gen:{name} -->" in text, page


def test_no_secrets_in_docs():
    text = _all_docs_text()
    for pat in (r"sk-[A-Za-z0-9]{20,}", r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}", r"cagatay4321", r"AKIA[0-9A-Z]{16}"):
        assert not re.search(pat, text), f"secret-looking string in docs: {pat}"


def test_no_cockpit_hostname_in_docs():
    """Owner directive (2026-09-21): the cockpit host is his alone — the docs never name it or link to it."""
    hits = []
    for p in list(DOCS.rglob("*.md")) + list(DOCS.rglob("*.html")) + list(DOCS.rglob("*.js")):
        if "assets" in p.parts:
            continue
        if "cagatay.my" in p.read_text(encoding="utf-8", errors="ignore"):
            hits.append(str(p.relative_to(DOCS)))
    assert not hits, hits
