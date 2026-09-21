#!/usr/bin/env python3
"""routedoc — the dashboard HTTP/WS API table, generated from dashboard/server.py.

Finds every `@app.get/post/put/delete/websocket("...")` in `create_app()`, the
handler's name, its query/body parameters (from the signature), its docstring
or the comment above it, and whether the gate lets anonymous callers in
(`PUBLIC_API` + `/api/auth/*` in `_gate`). Emits a Markdown table grouped by
area — nothing about the API is typed by hand.

Usage:  python scripts/routedoc.py            # Markdown to stdout
        python scripts/routedoc.py --json
Stdlib only; never imports the dashboard.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SERVER = ROOT / "dashboard" / "server.py"
AUTH = ROOT / "dashboard" / "auth.py"
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from routedoc_notes import NOTES  # type: ignore
except Exception:  # pragma: no cover
    NOTES = {}

GROUPS = [
    ("Health & state", r"^/api/(health|state|telemetry|emotions|log|ask/last)$"),
    ("Camera", r"^/api/(stream|snapshot\.jpg|camera/.*)$"),
    ("Control", r"^/api/control/.*"),
    ("Ask / chat", r"^/api/chat$"),
    ("Perception", r"^/api/tracking.*"),
    ("Auth", r"^/api/auth/.*"),
    ("Realtime", r"^/ws$"),
    ("Shell", r"^/($|\{path:path\})"),
]


def _public_set(src: str) -> set[str]:
    m = re.search(r"PUBLIC_API\s*=\s*(\{[^}]*\})", src)
    return set(ast.literal_eval(m.group(1))) if m else set()


def _body_keys(fn: ast.AST) -> list[str]:
    """Keys the handler reads from the JSON body: body.get("k"), body["k"], _num(body, "k")."""
    keys: list[str] = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute) and f.attr == "get" and isinstance(f.value, ast.Name) and f.value.id == "body" and n.args:
                k = n.args[0]
            elif isinstance(f, ast.Name) and f.id == "_num" and len(n.args) >= 2 and isinstance(n.args[0], ast.Name) and n.args[0].id == "body":
                k = n.args[1]
            else:
                continue
            if isinstance(k, ast.Constant) and isinstance(k.value, str) and k.value not in keys:
                keys.append(k.value)
        elif isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id == "body" and isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str):
            if n.slice.value not in keys:
                keys.append(n.slice.value)
    return keys


def _params(fn: ast.AST) -> str:
    out = []
    for a in fn.args.args + fn.args.kwonlyargs:
        if a.arg in ("req", "request", "ws", "websocket", "self"):
            continue
        ann = ast.unparse(a.annotation) if a.annotation else ""
        if "Body" in ann or a.arg == "body":
            keys = _body_keys(fn)
            out.append("JSON " + "{" + ", ".join(keys) + "}" if keys else "JSON body")
        else:
            out.append(f"`{a.arg}`" + (f": {ann}" if ann else ""))
    return ", ".join(out) or "—"


def _comment_above(lines: list[str], lineno: int) -> str:
    i = lineno - 2
    while i >= 0 and lines[i].strip().startswith("#"):
        i -= 1
    if i + 1 <= lineno - 2:
        txt = " ".join(l.strip().lstrip("#").strip(" ─-") for l in lines[i + 1:lineno - 1])
        return txt.strip()
    return ""


def routes() -> list[dict]:
    src = SERVER.read_text(encoding="utf-8")
    lines = src.splitlines()
    tree = ast.parse(src)
    public = _public_set(src)
    found: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr in ("get", "post", "put", "delete", "websocket", "api_route") and dec.args:
                path = ast.literal_eval(dec.args[0])
                method = dec.func.attr.upper() if dec.func.attr != "websocket" else "WS"
                doc = (ast.get_docstring(node) or "").strip().split("\n")[0]
                if not doc:
                    doc = _comment_above(lines, dec.lineno)
                anon = path in public or path.startswith("/api/auth/") or not (path.startswith("/api/") or path == "/ws")
                doc = NOTES.get(f"{method} {path}", doc)
                found.append({"method": method, "path": path, "handler": node.name, "params": _params(node),
                              "doc": doc, "public": anon, "line": dec.lineno})
    # auth router lives in auth.py — pick up its routes too
    if AUTH.exists():
        asrc = AUTH.read_text(encoding="utf-8")
        for m in re.finditer(r'@(?:router|app)\.(get|post|delete)\("([^"]+)"\)\s*\n\s*(?:async )?def (\w+)', asrc):
            path = m.group(2) if m.group(2).startswith("/api") else "/api/auth" + m.group(2)
            found.append({"method": m.group(1).upper(), "path": path, "handler": m.group(3), "params": "—",
                          "doc": NOTES.get(f"{m.group(1).upper()} {path}", ""), "public": True, "line": asrc[:m.start()].count("\n") + 1, "file": "dashboard/auth.py"})
    found.sort(key=lambda r: (r["path"], r["method"]))
    return found


def markdown(rs: list[dict]) -> str:
    lines = ["<!-- generated by scripts/routedoc.py from dashboard/server.py (+ auth.py) — edit the code, not this table -->", ""]
    seen = set()
    for title, pat in GROUPS:
        rows = [r for r in rs if re.match(pat, r["path"]) and id(r) not in seen]
        if not rows:
            continue
        lines += [f"### {title}", "", "| method | path | params | anonymous? | what |", "|---|---|---|---|---|"]
        for r in rows:
            seen.add(id(r))
            f = r.get("file", "dashboard/server.py")
            src = f'<a href="https://github.com/cagataycali/tiny-the-reachy/blob/main/{f}#L{r["line"]}">src</a>'
            lines.append(f"| `{r['method']}` | `{r['path']}` | {r['params']} | {'✅ public' if r['public'] else '🔒 key'} | {r['doc'].replace('|', '\\|') or '—'} · {src} |")
        lines.append("")
    rest = [r for r in rs if id(r) not in seen]
    if rest:
        lines += ["### Other", "", "| method | path | params | anonymous? | what |", "|---|---|---|---|---|"]
        lines += [f"| `{r['method']}` | `{r['path']}` | {r['params']} | {'✅ public' if r['public'] else '🔒 key'} | {r['doc'] or '—'} |" for r in rest]
        lines.append("")
    n_pub = sum(1 for r in rs if r["public"])
    lines.append(f"_{len(rs)} routes; {n_pub} answer without a key (health, the auth handshake and the SPA shell), the rest 401 anonymous callers and close a WebSocket with 4401._")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    rs = routes()
    if "--json" in sys.argv:
        print(json.dumps(rs, indent=2))
    else:
        sys.stdout.write(markdown(rs))
