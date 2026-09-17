"""mkdocs hook: regenerate the code-derived pages before every build so they cannot rot.

- docs/reference/tools/*.md   ← scripts/tooldoc.py   (every @tool: signature + docstring)
- docs/reference/env.md       ← scripts/envdoc.py    (every os.getenv in the repo)
- docs/reference/api.md       ← scripts/routedoc.py  (every dashboard route + gate)

Each target page is a hand-written shell containing the marker pair
`<!-- gen:NAME -->` … `<!-- /gen:NAME -->`; only the inside is replaced, so the prose around
the tables stays editable. Stdlib only — the docs venv never imports the robot code.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import envdoc, routedoc, tooldoc  # noqa: E402


def _splice(path: pathlib.Path, name: str, body: str) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    pat = re.compile(rf"(<!-- gen:{name} -->).*?(<!-- /gen:{name} -->)", re.S)
    if not pat.search(text):
        raise SystemExit(f"{path}: missing <!-- gen:{name} --> markers")
    new = pat.sub(lambda m: m.group(1) + "\n" + body.strip("\n") + "\n" + m.group(2), text)
    if new != text:
        path.write_text(new, encoding="utf-8")


def on_pre_build(config, **kwargs):
    tooldoc.write(tooldoc.build())
    _splice(ROOT / "docs" / "reference" / "env.md", "env", envdoc.markdown(envdoc.collect()))
    _splice(ROOT / "docs" / "reference" / "api.md", "api", routedoc.markdown(routedoc.routes()))
