"""Runtime config store — the knobs the cockpit Settings sheet edits while TINY runs.

One SQLite table in .memory/mem.db (next to prompts/memory/agent_log) holds the owner's
overrides; the env var stays the bootstrap default. Every persona resolves a knob with
``cfg(key)`` at BUILD time, so the resolution order is always:

    config DB value  ->  env var (.env)  ->  code default

Keys are declared once in SCHEMA (group, type, choices, range, help, restart scope); the
dashboard generates its Settings UI from ``schema()`` and validates PUTs with
``validate()``. Never in this store: API keys, bot tokens, REACHY_* host/port/token.

Restart scopes: a write to a key with ``restart="voice"`` bumps the ``voice`` generation
counter; voice_listener polls ``generation("voice")`` and rebuilds its live session.
``restart="agent"`` bumps ``agent`` (the thinker rebuilds its Agent on the next cycle;
telegram and the dashboard Ask build a fresh Agent per message anyway).

Schema:
  config(key PRIMARY KEY, value TEXT json, updated_at, updated_by)
  config_history(id, key, old TEXT json, new TEXT json, ts, source)
  config_meta(scope PRIMARY KEY, generation INTEGER)

Persona prompt notes (``agent.prompt_note.<persona>``) are virtual keys backed by
tools/prompts.py (same table + history the `prompts` tool uses) so there is ONE source.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

DB = Path(__file__).resolve().parent.parent / ".memory" / "mem.db"

PERSONAS = ("voice", "telegram", "thinker", "dashboard")       # the four the cockpit shows
PROMPT_PERSONAS = ("voice", "telegram", "thinker", "shell")    # tools/prompts.VALID_PERSONAS
SCOPES = ("voice", "agent", "none")

_lock = threading.Lock()


@dataclass(frozen=True)
class Key:
    name: str                       # "voice.provider"
    group: str                      # voice | agent | telegram
    type: str                       # str | text | int | float | bool | choice | list
    label: str
    help: str
    default: Any = None
    env: Optional[Callable[[], Any]] = None   # a lambda with a LITERAL os.getenv(...) so scripts/envdoc.py sees it
    choices: tuple = ()
    min: Optional[float] = None
    max: Optional[float] = None
    restart: str = "none"           # voice | agent | none
    dangerous: bool = False
    virtual: str = ""               # "prompt:<persona>" → stored by tools/prompts.py, not here

    def to_json(self) -> Dict[str, Any]:
        return {"key": self.name, "group": self.group, "type": self.type, "label": self.label, "help": self.help,
                "default": self.default, "choices": list(self.choices), "min": self.min, "max": self.max,
                "restart": self.restart, "dangerous": self.dangerous, "virtual": bool(self.virtual)}


def _csv_list(raw: str) -> List[str]:
    return [u.strip() for u in (raw or "").split(",") if u.strip()]


_PROVIDER_ALIAS = {"openai_realtime": "openai", "nova": "nova_sonic", "novasonic": "nova_sonic", "gemini_live": "gemini"}


def _provider(raw: str) -> str:
    s = (raw or "openai").strip().lower()
    return _PROVIDER_ALIAS.get(s, s)


def _env_bool(raw: str, default: bool) -> bool:
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "on", "yes")


def _schema() -> List[Key]:
    k: List[Key] = []
    # ── voice (restart scope: voice — the live Realtime session is rebuilt) ──
    k += [
        Key("voice.provider", "voice", "choice", "provider", "Realtime provider for the voice persona.",
            default="openai", env=lambda: _provider(os.getenv("VOICE_PROVIDER", "openai")),
            choices=("openai", "nova_sonic", "gemini"), restart="voice"),
        Key("voice.model", "voice", "str", "model", "Realtime model id (empty = the provider's default).",
            default="", env=lambda: os.getenv("VOICE_MODEL", ""), restart="voice"),
        Key("voice.name", "voice", "str", "voice", "Voice name (openai: alloy/ash/coral/shimmer...; nova: tiffany/matthew; gemini: Kore...). Empty = default.",
            default="", env=lambda: os.getenv("VOICE_NAME", ""), restart="voice"),
        Key("voice.lang", "voice", "str", "language", "ISO-639-1 for input transcription (tr, en). Empty = auto-detect.",
            default="", env=lambda: os.getenv("VOICE_LANG", ""), restart="voice"),
        Key("voice.transcribe_prompt", "voice", "text", "transcriber hint", "Free-text hint for the transcriber (names, languages).",
            default="", env=lambda: os.getenv("VOICE_TRANSCRIBE_PROMPT", ""), restart="voice"),
        Key("voice.turn_detection", "voice", "choice", "turn detection", "server_vad (silence based) or semantic_vad (meaning based).",
            default="server_vad", env=lambda: os.getenv("VOICE_TURN_DETECTION", "server_vad"),
            choices=("server_vad", "semantic_vad"), restart="voice"),
        Key("voice.vad_threshold", "voice", "float", "VAD threshold", "server_vad speech threshold 0..1 (higher = needs louder speech).",
            default=0.5, env=lambda: os.getenv("VOICE_VAD_THRESHOLD", "0.5"), min=0.0, max=1.0, restart="voice"),
        Key("voice.vad_silence_ms", "voice", "int", "end-of-turn silence (ms)", "Silence that ends the user's turn.",
            default=600, env=lambda: os.getenv("VOICE_VAD_SILENCE_MS", "600"), min=100, max=5000, restart="voice"),
        Key("voice.vad_prefix_ms", "voice", "int", "prefix padding (ms)", "Audio kept before speech onset.",
            default=300, env=lambda: os.getenv("VOICE_VAD_PREFIX_MS", "300"), min=0, max=2000, restart="voice"),
        Key("voice.vad_eagerness", "voice", "choice", "eagerness", "semantic_vad only: how fast the model takes its turn.",
            default="auto", env=lambda: os.getenv("VOICE_VAD_EAGERNESS", "auto"),
            choices=("low", "medium", "high", "auto"), restart="voice"),
    ]
    # ── agent ──
    k += [
        Key("agent.model_id", "agent", "str", "model id", "Bedrock model for telegram / thinker / shell / dashboard Ask.",
            default="global.anthropic.claude-opus-4-8", env=lambda: os.getenv("TINY_MODEL_ID", "global.anthropic.claude-opus-4-8"),
            restart="agent"),
        Key("agent.fleet_tools", "agent", "bool", "fleet tools", "Mount the tiny.technology fleet tools (use_device & co) for the personas listed in TINY_MCP_PERSONAS.",
            default=False, env=lambda: _env_bool(os.getenv("TINY_MCP", "0"), False), restart="voice"),
    ]
    for p in PROMPT_PERSONAS:
        k.append(Key(f"agent.prompt_note.{p}", "agent", "text", f"{p} note",
                     "Personality note appended to the code prompt. Start with FULL: to replace the whole prompt (not recommended).",
                     default="", restart="voice" if p == "voice" else "none", virtual=f"prompt:{p}"))
    for p in PERSONAS:
        k.append(Key(f"agent.tools.{p}", "agent", "list", f"{p} tools",
                     "Tool names this persona gets. Empty list = the code default. Unknown names are ignored with a warning.",
                     default=None, restart="voice" if p == "voice" else "agent"))
    # ── telegram (fresh Agent per message, so no restart; the voice prompt embeds chat id + owner → voice) ──
    k += [
        Key("telegram.default_chat_id", "telegram", "str", "default chat id", "Where telegram() sends when no chat_id is given; the thinker's heartbeat target.",
            default="", env=lambda: os.getenv("TELEGRAM_DEFAULT_CHAT_ID", ""), restart="voice"),
        Key("telegram.allowed_users", "telegram", "list", "allowed users", "Usernames or numeric ids the listener answers. Empty = everyone. First entry = the owner the voice persona addresses.",
            default=[], env=lambda: _csv_list(os.getenv("TELEGRAM_ALLOWED_USERS", "")), restart="voice"),
        Key("telegram.heartbeat_photos", "telegram", "bool", "heartbeat photos", "The thinker sends a photo + caption every cycle (off = journal only).",
            default=True, env=lambda: _env_bool(os.getenv("THINKER_HEARTBEAT_PHOTOS", "1"), True)),
    ]
    return k


SCHEMA: Dict[str, Key] = {key.name: key for key in _schema()}
# tool names the UI flags with an amber note (they run code / spawn agents / mutate the toolset)
DANGEROUS_TOOLS = ("shell", "dispatch", "manage_tools", "environment", "use_device")


def schema() -> List[Dict[str, Any]]:
    return [k.to_json() for k in SCHEMA.values()]


# ── storage ───────────────────────────────────────────────────────────
def _conn() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=5)
    c.execute("PRAGMA busy_timeout=5000")
    c.executescript("""
        CREATE TABLE IF NOT EXISTS config(
            key TEXT PRIMARY KEY, value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_by TEXT);
        CREATE TABLE IF NOT EXISTS config_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL, old TEXT, new TEXT,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP, source TEXT);
        CREATE TABLE IF NOT EXISTS config_meta(scope TEXT PRIMARY KEY, generation INTEGER NOT NULL DEFAULT 0);
    """)
    return c


def _prompts():
    # the package re-exports the `prompts` TOOL under the same name, so fetch the MODULE explicitly
    import importlib  # noqa: PLC0415
    return importlib.import_module(__name__.rsplit(".", 1)[0] + ".prompts")


def _virtual_get(key: Key) -> Optional[str]:
    persona = key.virtual.split(":", 1)[1]
    return _prompts().get_override(persona)


def _stored() -> Dict[str, Any]:
    """Every override in the DB (raw), decoded. Missing DB → {}."""
    if not DB.exists():
        return {}
    c = _conn()
    try:
        rows = c.execute("SELECT key, value FROM config").fetchall()
    except sqlite3.OperationalError:
        return {}
    finally:
        c.close()
    out: Dict[str, Any] = {}
    for k, v in rows:
        try:
            out[k] = json.loads(v)
        except (TypeError, ValueError):
            continue
    return out


def env_value(key: str) -> Any:
    """The bootstrap value: env var (via the schema's getenv lambda) or the code default. Coerced to the key's type."""
    k = SCHEMA[key]
    if k.env is None:
        return k.default
    try:
        raw = k.env()
    except Exception:  # noqa: BLE001
        return k.default
    try:
        return validate(key, raw)
    except ValueError:
        return k.default


def get(key: str, default: Any = None) -> Any:
    """config DB → env → code default. Unknown key → ``default``."""
    k = SCHEMA.get(key)
    if k is None:
        return default
    if k.virtual:
        v = _virtual_get(k)
        return v if v is not None else (default if default is not None else k.default)
    stored = _stored()
    if key in stored:
        try:
            return validate(key, stored[key])
        except ValueError:
            pass
    v = env_value(key)
    return v if v is not None else default


cfg = get   # the short spelling used at build sites: cfg("voice.provider")


def get_all() -> Dict[str, Any]:
    """{key: effective value} for every schema key."""
    return {name: get(name) for name in SCHEMA}


def overrides() -> Dict[str, Any]:
    """{key: value} for keys the owner overrode (DB rows + prompt notes present)."""
    out = {k: v for k, v in _stored().items() if k in SCHEMA}
    for name, k in SCHEMA.items():
        if k.virtual:
            v = _virtual_get(k)
            if v is not None:
                out[name] = v
    return out


def _short(v: Any, n: int = 80) -> str:
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return s if len(s) <= n else s[: n - 1] + "…"


def set_many(values: Dict[str, Any], by: str = "dashboard") -> Dict[str, Any]:
    """Validate and store every key; bump the generation of each restart scope touched.

    Returns {"changed": {key: {"old":..,"new":..}}, "generations": {scope: n}, "restart": [scopes]}.
    Raises ValueError (one message per bad key, joined) before writing anything.
    """
    errors: List[str] = []
    clean: Dict[str, Any] = {}
    for key, raw in values.items():
        if key not in SCHEMA:
            errors.append(f"{key}: unknown key")
            continue
        try:
            clean[key] = validate(key, raw)
        except ValueError as e:
            errors.append(f"{key}: {e}")
    if errors:
        raise ValueError("; ".join(errors))

    changed: Dict[str, Dict[str, Any]] = {}
    scopes: set = set()
    with _lock:
        before = get_all()
        # prompt notes live in tools/prompts.py (its own connection, commits per call) — write them BEFORE
        # opening our connection, or the two writers deadlock on the same SQLite file
        for key, value in clean.items():
            k = SCHEMA[key]
            if k.virtual:
                persona = k.virtual.split(":", 1)[1]
                if value in ("", None):
                    _prompts().reset_override(persona)
                else:
                    _prompts().set_override(persona, value, source=by)
        c = _conn()
        try:
            for key, value in clean.items():
                k = SCHEMA[key]
                old = before.get(key)
                if not k.virtual:
                    c.execute("INSERT INTO config(key, value, updated_by) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET "
                              "value=excluded.value, updated_at=CURRENT_TIMESTAMP, updated_by=excluded.updated_by",
                              (key, json.dumps(value), by))
                if old != value:
                    c.execute("INSERT INTO config_history(key, old, new, source) VALUES(?,?,?,?)",
                              (key, json.dumps(old), json.dumps(value), by))
                    changed[key] = {"old": _short(old), "new": _short(value)}
                    if k.restart in ("voice", "agent"):
                        scopes.add(k.restart)
            for scope in scopes:
                c.execute("INSERT INTO config_meta(scope, generation) VALUES(?,1) ON CONFLICT(scope) DO UPDATE SET "
                          "generation=generation+1", (scope,))
            c.commit()
        finally:
            c.close()
    return {"changed": changed, "generations": generations(), "restart": sorted(scopes)}


def reset(key: str, by: str = "dashboard") -> bool:
    """Drop the override: the key falls back to env / code default. True if something was removed."""
    k = SCHEMA.get(key)
    if k is None:
        raise ValueError(f"{key}: unknown key")
    with _lock:
        old = get(key)
        if k.virtual:
            removed = _prompts().reset_override(k.virtual.split(":", 1)[1])
        else:
            c = _conn()
            try:
                removed = bool(c.execute("DELETE FROM config WHERE key=?", (key,)).rowcount)
                c.commit()
            finally:
                c.close()
        if removed:
            new = get(key)
            c = _conn()
            try:
                c.execute("INSERT INTO config_history(key, old, new, source) VALUES(?,?,?,?)",
                          (key, json.dumps(old), json.dumps(new), f"{by}:reset"))
                if k.restart in ("voice", "agent") and old != new:
                    c.execute("INSERT INTO config_meta(scope, generation) VALUES(?,1) ON CONFLICT(scope) DO UPDATE SET "
                              "generation=generation+1", (k.restart,))
                c.commit()
            finally:
                c.close()
    return bool(removed)


def generation(scope: str = "voice") -> int:
    """Monotonic counter bumped by every write to a key with that restart scope. 0 when nothing was ever written."""
    if not DB.exists():
        return 0
    c = _conn()
    try:
        row = c.execute("SELECT generation FROM config_meta WHERE scope=?", (scope,)).fetchone()
    except sqlite3.OperationalError:
        return 0
    finally:
        c.close()
    return int(row[0]) if row else 0


def generations() -> Dict[str, int]:
    return {s: generation(s) for s in ("voice", "agent")}


def history(key: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    if not DB.exists():
        return []
    c = _conn()
    try:
        if key:
            rows = c.execute("SELECT id, key, old, new, ts, source FROM config_history WHERE key=? ORDER BY id DESC LIMIT ?",
                             (key, limit)).fetchall()
        else:
            rows = c.execute("SELECT id, key, old, new, ts, source FROM config_history ORDER BY id DESC LIMIT ?",
                             (limit,)).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        c.close()
    out = []
    for i, k, old, new, ts, src in rows:
        try:
            out.append({"id": i, "key": k, "old": json.loads(old) if old else None,
                        "new": json.loads(new) if new else None, "ts": ts, "source": src})
        except ValueError:
            continue
    return out


# ── validation ────────────────────────────────────────────────────────
def validate(key: str, raw: Any) -> Any:
    """Coerce ``raw`` to the key's type and check choices/range. ValueError with a human sentence otherwise."""
    k = SCHEMA.get(key)
    if k is None:
        raise ValueError("unknown key")
    t = k.type
    if t in ("str", "text"):
        if raw is None:
            return ""
        if not isinstance(raw, str):
            raise ValueError("must be text")
        s = raw if t == "text" else raw.strip()
        if t == "str" and ("\n" in s or len(s) > 200):
            raise ValueError("one line, at most 200 characters")
        if t == "text" and len(s) > 8000:
            raise ValueError("at most 8000 characters")
        return s
    if t == "choice":
        if not isinstance(raw, str):
            raise ValueError(f"must be one of {', '.join(k.choices)}")
        s = raw.strip().lower()
        if s not in k.choices:
            raise ValueError(f"must be one of {', '.join(k.choices)}")
        return s
    if t == "bool":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str) and raw.strip().lower() in ("1", "true", "on", "yes", "0", "false", "off", "no", ""):
            return raw.strip().lower() in ("1", "true", "on", "yes")
        if isinstance(raw, (int, float)) and raw in (0, 1):
            return bool(raw)
        raise ValueError("must be true or false")
    if t in ("int", "float"):
        if isinstance(raw, bool):
            raise ValueError("must be a number")
        try:
            v = float(raw) if isinstance(raw, (int, float, str)) and str(raw).strip() != "" else None
        except ValueError:
            v = None
        if v is None or v != v or v in (float("inf"), float("-inf")):
            raise ValueError("must be a number")
        if t == "int":
            if v != int(v):
                raise ValueError("must be a whole number")
            v = int(v)
        if k.min is not None and v < k.min:
            raise ValueError(f"must be at least {k.min:g}")
        if k.max is not None and v > k.max:
            raise ValueError(f"must be at most {k.max:g}")
        return v
    if t == "list":
        if raw is None:
            return None if k.default is None else []
        if isinstance(raw, str):
            items = [x.strip() for x in raw.replace("\n", ",").split(",")]
        elif isinstance(raw, (list, tuple)):
            items = [str(x).strip() for x in raw]
        else:
            raise ValueError("must be a list (or one item per line)")
        items = [x.lstrip("@") if key == "telegram.allowed_users" else x for x in items if x]
        if len(items) > 200:
            raise ValueError("at most 200 entries")
        for x in items:
            if len(x) > 120:
                raise ValueError("entries are at most 120 characters")
        # an empty tools list means "code default" (None); an empty allowlist means "everyone" ([])
        if key.startswith("agent.tools.") and not items:
            return None
        return items
    raise ValueError(f"unsupported type {t}")


# ── convenience readers used by the personas ─────────────────────────
def telegram_default_chat_id() -> str:
    return str(get("telegram.default_chat_id") or "")


def telegram_allowed() -> set:
    return set(get("telegram.allowed_users") or [])


def tools_for(persona: str, catalog: Iterable[str]) -> Optional[List[str]]:
    """The configured tool names for a persona, or None for the code default.

    Names not in ``catalog`` are dropped with a warning on stderr (a typo must not kill a persona)."""
    names = get(f"agent.tools.{persona}")
    if not names:
        return None
    cat = set(catalog)
    keep = [n for n in names if n in cat]
    unknown = [n for n in names if n not in cat]
    if unknown:
        import sys  # noqa: PLC0415
        print(f"[config] agent.tools.{persona}: ignoring unknown tool names {unknown}", file=sys.stderr)
    return keep


def key_present_in_env(name: str) -> bool:
    """For the UI's 'OPENAI_API_KEY: set/unset' line — a boolean only, the value never leaves the server."""
    return bool(os.environ.get(name))
