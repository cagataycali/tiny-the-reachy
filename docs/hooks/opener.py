"""mkdocs hook: the page opener — eyebrow · H1 · dek · chip row — generated from nav + front-matter, never typed by hand.

    <p class="eyebrow">Get started</p>                    ← nav section the page lives in
    # Quickstart                                          ← the page's own H1, untouched
    <p class="dek">Clone, pick a model, first wobble …</p> ← front-matter `description:` (also the og:description)
    <ul class="page-meta"> for operators · 3 min · 540 words · proven on the robot · verified 2026-09-17 </ul>
                                                          ← `for:` audience, reading time, `status:` robot|sim|code|stale, `verified:` date

Also publishes the build ledger the footer strip renders (config.extra.ledger: tool count from scripts/tooldoc.py, source commit,
daemon/MuJoCo versions) so those numbers are never typed twice. Opt out per page with `hide_opener: true`;
pages with `template:` (the landing) are skipped. Text rendered here is template output — not markdown anyone maintains.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

_H1 = re.compile(r"^# .+$", re.M)
_WORD = re.compile(r"[A-Za-z0-9][\w'’.-]*")
_STATUS = {"robot": "proven on the robot", "sim": "proven in sim", "code": "from the code", "stale": "needs re-check"}
DAEMON = "1.10"       # reachy-mini daemon on the CM4 (tools/head_tracking.py needs ≥ 1.10 for the face tracker)
MUJOCO = "3.13.0"     # dashboard/frontend/public/model/twin.xml was solved with this (home.html chapter 4)


def count_words(markdown: str) -> int:
    text = re.sub(r"```.*?```", " ", markdown, flags=re.S)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"^---\n.*?\n---\n", " ", text, flags=re.S)
    return len(_WORD.findall(text))


def reading_time(words: int) -> str:
    m = max(1, round(words / 220))
    return f"{m} min"


def _section(page) -> str:
    parent = getattr(page, "parent", None)
    if parent is None or not getattr(parent, "title", None):
        return ""
    if getattr(page, "is_index", False) and parent.title.lower() == page.title.lower():
        return ""
    return parent.title


def _hero(page, words: int) -> tuple[str, str]:
    section = _section(page)
    before = f'<p class="eyebrow">{section}</p>\n\n' if section else ""
    chips = []
    who = page.meta.get("for")
    if who:
        chips.append(f'<li class="chip chip--for">{who}</li>')
    chips.append(f'<li class="chip">{reading_time(words)}</li>')
    chips.append(f'<li class="chip">{words} words</li>')
    status = str(page.meta.get("status", "")).lower()
    if status in _STATUS:
        chips.append(f'<li class="chip chip--status chip--{status}">{_STATUS[status]}</li>')
    verified = page.meta.get("verified")
    if verified:
        chips.append(f'<li class="chip">verified {verified}</li>')
    desc = page.meta.get("description")
    dek = f'<p class="dek">{desc}</p>\n' if desc else ""
    meta = '<ul class="page-meta" aria-label="audience, reading time and status">' + "".join(chips) + "</ul>"
    return before, dek + meta


def on_config(config, **kwargs):
    ledger = {"daemon": DAEMON, "mujoco": MUJOCO, "tools": "?", "modules": "?", "commit": ""}
    try:
        import tooldoc  # noqa: E402  (stdlib AST scan of tools/*.py)
        inv = tooldoc.inventory()
        ledger["tools"] = sum(len(v["tools"]) for v in inv.values())
        ledger["modules"] = len(inv)
    except Exception:  # the docs venv may not see scripts/ in some CI layouts — the strip then shows "?" rather than a wrong number
        pass
    try:
        ledger["commit"] = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        pass
    config.extra["ledger"] = ledger
    return config


def on_page_markdown(markdown: str, page, config, files):
    words = count_words(markdown)
    page.meta["word_count"] = words
    page.meta["reading_time"] = reading_time(words)
    if page.meta.get("template") or page.meta.get("hide_opener"):
        return markdown
    before, after = _hero(page, words)
    m = _H1.search(markdown)
    if m:
        return markdown[: m.start()] + before + markdown[m.start() : m.end()] + "\n\n" + after + "\n" + markdown[m.end() :]
    return before + after + "\n\n" + markdown
