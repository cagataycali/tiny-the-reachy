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
MODULES = {
    "reachy_motion": ("Motion", "head pose, antennas, body yaw, home, wake/sleep — every angle clamped before it reaches the daemon"),
    "reachy_expression": ("Expression", "the recorded-move library (emotions, dances) the personas fire while they talk"),
    "reachy_state": ("State", "read the live pose and switch motor modes"),
    "reachy_camera": ("Camera", "grab a frame, look at a pixel, ask the vision model a question about what TINY sees"),
    "reachy_audio": ("Audio", "speak (Piper TTS on the CM4), play a sound, set the speaker volume — “silent” means 0"),
    "head_tracking": ("Head tracking", "toggle the daemon's face tracker (reachy-mini ≥ 1.10) through the dashboard's tracking controller"),
    "turn_to_sound": ("Turn to sound", "turn toward whoever is talking (ReSpeaker direction of arrival) when face tracking has no lock — the dashboard's DoA turner"),
    "vision": ("Vision", "take_photo — a frame plus a question for the multimodal model, shared by every persona"),
    "voice_bridge": ("Voice bridge", "text → the voice persona's mouth (say/mute) from the text personas"),
    "dispatch": ("Dispatch", "hand a task to another persona (voice/telegram/thinker) through the shared brain"),
    "memory": ("Memory", "the cross-persona SQLite brain: remember, recall, forget"),
    "telegram": ("Telegram", "send text and photos to the owner's chat from any persona"),
    "prompts": ("Prompts", "read and override each persona's system prompt (override = personality note appended; `FULL:` replaces)"),
    "manage_messages": ("Manage messages", "inspect and compact the running agent's own conversation"),
    "manage_tools": ("Manage tools", "list, create and hot-load new tools at runtime"),
    "tiny_mcp": ("Fleet (tiny.technology MCP)", "use_device and the other fleet tools, mounted only when `TINY_MCP=1` — with the self-refusal guard"),
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


def render_module(mod: str, m: dict) -> str:
    n = len(m["tools"])
    lines = ["---", f"title: {m['title']}", f"description: \"{m['blurb'].replace('\"', '')}\"", "---", "", HEADER.format(mod=mod),
             f"# {m['title']}", "", f"*{m['blurb']}* — `{m['file']}`, {n} tool{'s' if n != 1 else ''}.", ""]
    if m["moddoc"]:
        first = m["moddoc"].strip().split("\n\n")[0].replace("\n", " ")
        lines += ['!!! abstract "From the module docstring"', "    " + first, ""]
    lines += ["| tool | does |", "|---|---|"]
    for t in m["tools"]:
        s = _sections(t["doc"])
        lines.append(f"| [`{t['name']}`](#{t['name'].lower()}) | {_first_sentence(s['summary']).replace('|', '\\|')} |")
    lines.append("")
    for t in m["tools"]:
        s = _sections(t["doc"])
        lines += [f"## `{t['name']}`", "", "```python", ("async " if t["async"] else "") + t["signature"], "```", ""]
        if s["summary"]:
            lines += [textwrap.dedent(s["summary"]).strip(), ""]
        if s.get("args"):
            tbl = _args_table(s["args"])
            if tbl:
                lines += [tbl]
            else:
                lines += ["```text", s["args"], "```", ""]
        for key, title in (("actions", "Actions"), ("safety", "Safety"), ("returns", "Returns"), ("note", "Notes"), ("env", "Environment")):
            if s.get(key):
                lines += [f"**{title}**", "", s[key] if key != "returns" else s[key], ""]
        if s.get("example"):
            lines += ["**Examples**", "", "```python", textwrap.dedent(s["example"]), "```", ""]
        lines += [f'<small>source: <a href="https://github.com/cagataycali/tiny-the-reachy/blob/main/{m["file"]}#L{t["line"]}">{m["file"]}:{t["line"]}</a></small>', ""]
    return "\n".join(lines).rstrip() + "\n"


def render_index(inv: dict[str, dict]) -> str:
    total = sum(len(m["tools"]) for m in inv.values())
    lines = ["---", "title: Tools reference", f"description: \"Every @tool TINY can call, generated from the code — {total} tools in {len(inv)} modules.\"",
             "---", "", "<!-- generated by scripts/tooldoc.py — edit the docstrings, not this page -->", "", "# Tools reference", "",
             f"**{total} tools in {len(inv)} modules**, generated from the `@tool` functions in `tools/` at every docs build "
             "(`scripts/tooldoc.py`): signatures come from the AST, descriptions from the docstrings the model itself reads. "
             "If a page here disagrees with the robot, the docstring is wrong — fix it there.", "",
             "| module | tools | what it covers |", "|---|---|---|"]
    for mod, m in inv.items():
        names = " ".join(f"`{t['name']}`" for t in m["tools"])
        lines.append(f"| [{m['title']}]({mod}.md) | {names} | {m['blurb']} |")
    lines += ["", "## Who gets what", "",
              "Two builders in `tiny.py` decide which of these a persona can call:", "",
              "- **`build_tools()`** — shell, telegram, thinker: everything above plus `use_github`/`use_spotify` when importable.",
              "- **`build_voice_tools()`** — voice and the dashboard Ask: the latency-slim list (motion, expression, state, camera, "
              "head tracking, `reachy_volume`, memory, prompts, dispatch, telegram, voice_say, take_photo) — see [Personas](../../showcase/personas.md).",
              "", "Fleet tools (`use_device`, `tiny_recall`, `tiny_learn`, …) ride along only when `TINY_MCP=1` and the persona is in "
              "`TINY_MCP_PERSONAS`, never on a turn that itself arrived from another device — see [Fleet](../../MCP.md).", ""]
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
