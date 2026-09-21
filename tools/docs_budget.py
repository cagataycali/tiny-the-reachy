#!/usr/bin/env python3
"""The docs word budget — CI gate. Owner directive 2026-09-21: cut 60 % of the copy, keep the soul.

    python3 tools/docs_budget.py           # per-page table + PASS/FAIL (exit 1 over budget)
    python3 tools/docs_budget.py --json    # machine-readable

Counting (ported from lord-the-ring tools/docs_scan_budget.py): "prose words" = the words a reader sees after removing
front matter, code fences, HTML tags, `--8<--` snippets resolved. Table pipes are not words. Collapsed `??? ` bodies COUNT
IN FULL here (deliberate deviation from the ring): the owner wants less, not hidden.

Scope: every docs/**/*.md except the landing (docs/index.md, owned by the HQ lane) and docs/overrides/.

Budgets (hard):
  PAGE_HAND   300   any hand-written page
  PAGE_SOUL   400   personas · start/robot · start/systemd — they carry the soul
  PAGE_TOOL   120   generated tools/<module>.md pages: signature + purpose + envelope table + one example
  PAGE_TOOLS_INDEX 200
  PAGE_TABLE  env.md · api.md — tables only: no paragraph outside the "In 10 seconds" box (checked as ≤ PAGE_TABLE_MAX words)
  SITE_TARGET 6400  = 40 % of the 16,007 measured at 7f46bc4

Ratchet: SITE_CEILING is the total the gate enforces TODAY. It is lowered in the same commit as every cut and may never be
raised; when it reaches SITE_TARGET the ratchet is gone. GRACE lists pages not yet rewritten — they are reported, not
failed, and the set only shrinks. Both live here so the number the CI enforces is the number in the repo.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

PAGE_HAND = 300
PAGE_SOUL = 400
PAGE_TOOL = 120
PAGE_TOOLS_INDEX = 200
PAGE_TABLE_MAX = {"reference/env.md": 1300, "reference/api.md": 650}  # tables only; 110 vars × (name+default+≤7 words+link) — see JOURNAL it5/it10
SITE_TARGET = 6400
SITE_CEILING = 7600      # ratchet — lower with every cut, never raise (16,044 → 12,102 it5 → 10,532 it6 → 9,582 it7 → 8,468 it8 → 8,2xx it9; it9 also fixed _TAG, which had hidden "(< 1.5 s) … > 60 %" spans — earlier totals were ~1–3 % low)
SOUL = {"showcase/personas.md", "start/robot.md", "start/systemd.md"}
TABLES = {"reference/env.md", "reference/api.md"}
SKIP = {"index.md", "scripts/README.md", "design-assets/README.md", "LIVE_DEPLOY.md"}  # landing (HQ lane) + mkdocs exclude_docs (dev notes, not pages)
GRACE: set[str] = set()  # every page has been rewritten under this budget (it9) — the set only ever shrinks, and it is now empty

_FENCE = re.compile(r"^(\s*)(```|~~~)")
_FRONT = re.compile(r"\A---\n.*?\n---\n", re.S)
_TAG = re.compile(r"</?[A-Za-z!][^<>]*>")   # a real tag, not "(< 1.5 s) … > 60 %" prose
_SNIPPET = re.compile(r'^\s*-{2}8<-{2}\s*"([^"]+)"\s*$')
_WORD = re.compile(r"[A-Za-z0-9\u00C0-\u024F][\w'’\-.]*", re.U)


def _resolve_snippet(name: str) -> str:
    for base in (DOCS, ROOT):
        p = base / name
        if p.exists():
            return p.read_text(encoding="utf-8")
    return ""


def visible_text(markdown: str, *, depth: int = 0) -> str:
    md = _FRONT.sub("", markdown, count=1)
    out: list[str] = []
    in_fence: str | None = None
    for line in md.splitlines():
        f = _FENCE.match(line)
        if in_fence:
            if f and f.group(2) == in_fence:
                in_fence = None
            continue
        if f:
            in_fence = f.group(2)
            continue
        m = _SNIPPET.match(line)
        if m and depth < 3:
            out.append(visible_text(_resolve_snippet(m.group(1)), depth=depth + 1))
            continue
        out.append(line)
    return _TAG.sub(" ", "\n".join(out))


def count_words(markdown: str) -> int:
    return len(_WORD.findall(visible_text(markdown)))


def has_tldr(markdown: str) -> bool:
    return re.search(r'^!!!\s+(tldr|abstract|summary)\b', markdown, re.M) is not None


def limit_for(rel: str) -> int:
    if rel in SOUL:
        return PAGE_SOUL
    if rel in TABLES:
        return PAGE_TABLE_MAX[rel]
    if rel == "reference/tools/index.md":
        return PAGE_TOOLS_INDEX
    if rel.startswith("reference/tools/"):
        return PAGE_TOOL
    return PAGE_HAND


def pages() -> list[str]:
    rels = []
    for p in sorted(DOCS.rglob("*.md")):
        rel = p.relative_to(DOCS).as_posix()
        if rel in SKIP or rel.startswith("overrides/"):
            continue
        rels.append(rel)
    return rels


def audit() -> tuple[list[dict], list[str], list[str]]:
    rows, problems, notes = [], [], []
    for rel in pages():
        md = (DOCS / rel).read_text(encoding="utf-8")
        words, lim = count_words(md), limit_for(rel)
        rows.append(dict(page=rel, words=words, limit=lim, tldr=has_tldr(md), grace=rel in GRACE))
        over = words > lim
        if over and rel in GRACE:
            notes.append(f"{rel}: {words} > {lim} (grace — not yet rewritten)")
        elif over:
            problems.append(f"{rel}: {words} prose words > {lim}")
        if not has_tldr(md) and rel not in GRACE:
            problems.append(f"{rel}: no `!!! abstract` In-10-seconds box")
    total = sum(r["words"] for r in rows)
    if total > SITE_CEILING:
        problems.append(f"site: {total} prose words > ceiling {SITE_CEILING} (target {SITE_TARGET})")
    return rows, problems, notes


def main(argv: list[str]) -> int:
    rows, problems, notes = audit()
    total = sum(r["words"] for r in rows)
    if "--json" in argv:
        print(json.dumps(dict(pages=rows, total=total, ceiling=SITE_CEILING, target=SITE_TARGET, problems=problems, notes=notes), indent=1))
    else:
        w = max(len(r["page"]) for r in rows)
        for r in sorted(rows, key=lambda r: -r["words"]):
            flag = "!!" if r["words"] > r["limit"] and not r["grace"] else ("~~" if r["words"] > r["limit"] else "  ")
            print(f"{flag} {r['page']:<{w}} {r['words']:>5} / {r['limit']:<4} {'tldr' if r['tldr'] else '----'}")
        print(f"\n{len(rows)} pages · {total} prose words · ceiling {SITE_CEILING} · target {SITE_TARGET} · grace {len(GRACE)}")
        for n in notes:
            print("note", n)
        for p in problems:
            print("FAIL", p)
        print("PASS" if not problems else f"FAIL — {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
