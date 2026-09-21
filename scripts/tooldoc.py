#!/usr/bin/env python3
"""tooldoc — the tools reference, generated from the `@tool` functions themselves.

For every `tools/*.py` module it finds each function decorated with `@tool`
(top-level or nested, sync or async), and emits one Markdown page per module
with the real signature (from the AST, defaults included) and the docstring
(Google style: summary, Args, Examples, Returns) — nothing typed by hand.

Usage:  python scripts/tooldoc.py                 # write docs/reference/tools/*.md + index
        python scripts/tooldoc.py --check         # exit 1 if the committed pages differ
        python scripts/tooldoc.py --json          # inventory to stdout
Stdlib only; never imports the robot code (no strands / SDK needed).
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
import sys
import textwrap

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT / "tools"
OUT_DIR = ROOT / "docs" / "reference" / "tools"

# module → (page title, one-line blurb shown on the index and page top)
MODULES = {  # (title, blurb ≤ 8 words — the index row and the page description)
    "reachy_motion": ("Motion", "head, antennas, body, wake — clamped"),
    "reachy_expression": ("Expression", "recorded moves, fired while talking"),
    "reachy_state": ("State", "pose and motor modes"),
    "reachy_camera": ("Camera", "frames, look-at, vision"),
    "reachy_audio": ("Audio", "speech, sounds, volume"),
    "head_tracking": ("Head tracking", "the daemon's face tracker"),
    "turn_to_sound": ("Turn to sound", "ReSpeaker direction of arrival"),
    "vision": ("Vision", "a frame plus a question"),
    "voice_bridge": ("Voice bridge", "text → voice persona queue"),
    "dispatch": ("Dispatch", "hand off to another persona"),
    "memory": ("Memory", "the shared SQLite brain"),
    "telegram": ("Telegram", "text and photos to the owner"),
    "prompts": ("Prompts", "override persona prompts"),
    "manage_messages": ("Manage messages", "compact the agent's history"),
    "manage_tools": ("Manage tools", "hot-load tools at runtime"),
    "tiny_mcp": ("Fleet", "`use_device` & co, `TINY_MCP=1` only"),
}


def _sig(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    a = fn.args
    parts: list[str] = []
    pos = a.posonlyargs + a.args
    defaults = [None] * (len(pos) - len(a.defaults)) + list(a.defaults)
    for arg, d in zip(pos, defaults):
        if arg.arg in ("self", "tool_context"):
            continue
        s = arg.arg + (f": {ast.unparse(arg.annotation)}" if arg.annotation else "")
        if d is not None:
            s += f" = {ast.unparse(d)}"
        parts.append(s)
    if a.vararg:
        parts.append("*" + a.vararg.arg)
    if a.kwonlyargs:
        if not a.vararg:
            parts.append("*")
        for arg, d in zip(a.kwonlyargs, a.kw_defaults):
            s = arg.arg + (f": {ast.unparse(arg.annotation)}" if arg.annotation else "")
            if d is not None:
                s += f" = {ast.unparse(d)}"
            parts.append(s)
    if a.kwarg:
        parts.append("**" + a.kwarg.arg)
    ret = f" -> {ast.unparse(fn.returns)}" if fn.returns else ""
    body = ", ".join(parts)
    if len(body) > 80:
        body = "\n    " + ",\n    ".join(parts) + ",\n"
    return f"{fn.name}({body}){ret}"


def _is_tool(dec: ast.AST) -> bool:
    if isinstance(dec, ast.Name):
        return dec.id == "tool"
    if isinstance(dec, ast.Call):
        return _is_tool(dec.func)
    if isinstance(dec, ast.Attribute):
        return dec.attr == "tool"
    return False


def _sections(doc: str) -> dict[str, str]:
    """Split a Google-style docstring into summary + named sections."""
    doc = textwrap.dedent(doc or "").strip()
    out: dict[str, str] = {"summary": ""}
    doc = doc
    cur = "summary"
    buf: list[str] = []
    for line in doc.splitlines():
        m = re.match(r"^(Args|Arguments|Returns|Examples?|Raises|Notes?|Actions|Safety|Env|Environment):\s*$", line.strip())
        if m:
            out[cur] = _trim(buf)
            cur = m.group(1).rstrip("s").lower() if m.group(1).startswith("Example") else m.group(1).lower()
            buf = []
        else:
            buf.append(line)
    out[cur] = _trim(buf)
    return out


def _trim(buf: list[str]) -> str:
    """Drop blank edge lines but keep the block's relative indentation (dedent later)."""
    while buf and not buf[0].strip():
        buf = buf[1:]
    while buf and not buf[-1].strip():
        buf = buf[:-1]
    return "\n".join(buf)


def _first_sentence(text: str) -> str:
    flat = " ".join(textwrap.dedent(text).strip().split("\n\n")[0].split())
    m = re.match(r"(.+?[.!?])(\s|$)", flat)
    return m.group(1) if m else flat


def _args_table(block: str) -> str:
    rows = []
    for line in textwrap.dedent(block).splitlines():
        m = re.match(r"^(\S[^:]*?):\s*(.*)$", line.strip())
        if m and not line.startswith((" ", "\t")) or (m and rows == []):
            rows.append([m.group(1), m.group(2)])
        elif rows and line.strip():
            rows[-1][1] += " " + line.strip()
    if not rows:
        return ""
    body = "\n".join(f"| `{n}` | {d.replace('|', '\\|')} |" for n, d in rows)
    return f"| argument | meaning |\n|---|---|\n{body}\n"


def scan_module(path: pathlib.Path) -> list[dict]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(_is_tool(d) for d in node.decorator_list):
            found.append({
                "name": node.name,
                "async": isinstance(node, ast.AsyncFunctionDef),
                "signature": _sig(node),
                "doc": ast.get_docstring(node) or "",
                "line": node.lineno,
            })
    found.sort(key=lambda t: t["line"])
    return found


def inventory() -> dict[str, dict]:
    inv: dict[str, dict] = {}
    for mod, (title, blurb) in MODULES.items():
        p = TOOLS_DIR / f"{mod}.py"
        if not p.exists():
            continue
        tools = scan_module(p)
        moddoc = ast.get_docstring(ast.parse(p.read_text(encoding="utf-8"))) or ""
        inv[mod] = {"title": title, "blurb": blurb, "file": f"tools/{mod}.py", "moddoc": moddoc, "tools": tools}
    # any @tool module we forgot to list → surfaces on the index so it cannot rot silently
    for p in sorted(TOOLS_DIR.glob("*.py")):
        mod = p.stem
        if mod in inv or mod.startswith("_") or mod == "__init__":
            continue
        tools = scan_module(p)
        if tools:
            inv[mod] = {"title": mod, "blurb": "(module not yet described in scripts/tooldoc.py MODULES)",
                        "file": f"tools/{mod}.py", "moddoc": ast.get_docstring(ast.parse(p.read_text())) or "", "tools": tools}
    return inv


HEADER = "<!-- generated by scripts/tooldoc.py from tools/{mod}.py — edit the docstrings, not this page -->\n"


_ENVELOPE = re.compile(r"\[\s*-?\d|clamp|±|\b0[–-]1\b|\d+\s*[–-]\s*\d+\s*(deg|mm|s|%)", re.I)  # a stated range or clamp — not every unit


def _envelope_rows(block: str) -> str:
    """Only the argument rows that carry a range, unit or clamp — the envelope. Prose about meaning stays in the docstring."""
    tbl = _args_table(block)
    if not tbl:
        return ""
    rows = [ln for ln in tbl.splitlines()[2:] if _ENVELOPE.search(ln)]
    if not rows:
        return ""
    return "| argument | envelope |\n|---|---|\n" + "\n".join(rows) + "\n"


def _one_example(block: str) -> str:
    for ln in textwrap.dedent(block).splitlines():
        if ln.strip() and not ln.strip().startswith("#"):
            return ln.strip()
    return ""


def render_module(mod: str, m: dict) -> str:
    """Budget: ≤ 120 prose words per module page (tools/docs_budget.py). Signature + first sentence + envelope table + one example.
    The full docstring is what the model reads; the source link is one click."""
    n = len(m["tools"])
    names = " · ".join(f"`{t['name']}`" for t in m["tools"])
    lines = ["---", f"title: {m['title']}", f"description: \"{m['blurb'].replace('\"', '')}\"", "for: tool authors · prompt writers",
             "proof: code", "---", "", HEADER.format(mod=mod), f"# {m['title']}", "",
             '!!! abstract "In 10 seconds"',
             f"    - {n} tool{'s' if n != 1 else ''} in `{m['file']}` — {m['blurb']}.", ""]
    for t in m["tools"]:
        s = _sections(t["doc"])
        lines += [f"## `{t['name']}`", "", "```python", ("async " if t["async"] else "") + t["signature"], "```", ""]
        if s["summary"]:
            lines += [_first_sentence(textwrap.dedent(s["summary"]).strip()), ""]
        if s.get("args"):
            env = _envelope_rows(s["args"])
            if env:
                lines += [env]
        if s.get("example"):
            ex = _one_example(s["example"])
            if ex:
                lines += ["```python", ex, "```", ""]
        lines += [f'<small><a href="https://github.com/cagataycali/tiny-the-reachy/blob/main/{m["file"]}#L{t["line"]}" title="{m["file"]}:{t["line"]}">source ↗</a></small>', ""]
    return "\n".join(lines).rstrip() + "\n"


def render_index(inv: dict[str, dict]) -> str:
    """Budget: ≤ 160 prose words (tools/docs_budget.py)."""
    total = sum(len(m["tools"]) for m in inv.values())
    lines = ["---", "title: Tools reference", f"description: \"Every @tool TINY can call, generated from the code — {total} tools in {len(inv)} modules.\"",
             "for: tool authors · prompt writers", "proof: code",
             "---", "", "<!-- generated by scripts/tooldoc.py — edit the docstrings, not this page -->", "", "# Tools reference", "",
             '!!! abstract "In 10 seconds"',
             f"    - **{total} tools in {len(inv)} modules**, from the `@tool` docstrings.",
             "    - Who gets which: [Personas](../../showcase/personas.md).", "",
             '<div class="cards cards--3" markdown>', "", "| module | tools | covers |", "|---|---|---|"]
    for mod, m in inv.items():
        names = " ".join(f"`{t['name']}`" for t in m["tools"])
        lines.append(f"| [{m['title']}]({mod}.md) | {names} | {m['blurb']} |")  # row starts with a link, tools in column 2: tests/test_landing_tools.py reads it
    lines += ["", "</div>", ""]
    return "\n".join(lines)


def build() -> dict[str, str]:
    inv = inventory()
    pages = {f"{mod}.md": render_module(mod, m) for mod, m in inv.items()}
    pages["index.md"] = render_index(inv)
    return pages


def write(pages: dict[str, str]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in pages.items():
        path = OUT_DIR / name
        if not path.exists() or path.read_text(encoding="utf-8") != text:  # unchanged files keep their mtime: mkdocs serve
            path.write_text(text, encoding="utf-8")  # otherwise sees its own output as a change and rebuilds forever
    for stale in OUT_DIR.glob("*.md"):
        if stale.name not in pages:
            stale.unlink()


if __name__ == "__main__":
    if "--json" in sys.argv:
        print(json.dumps(inventory(), indent=2, default=str))
    elif "--check" in sys.argv:
        pages = build()
        bad = [n for n, t in pages.items() if not (OUT_DIR / n).exists() or (OUT_DIR / n).read_text() != t]
        if bad:
            print("stale generated pages:", ", ".join(bad))
            sys.exit(1)
        print("tools reference up to date")
    else:
        write(build())
        print(f"wrote {len(build())} pages to {OUT_DIR}")
