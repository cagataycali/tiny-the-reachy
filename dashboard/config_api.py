"""Runtime settings for the cockpit (Settings sheet): the logic behind /api/config and /api/personas.

The routes themselves live in :mod:`dashboard.server` (so scripts/routedoc.py documents them and the one
auth gate covers them); this module turns the config store (tools/config.py) into JSON the UI can render,
applies validated writes with an audit row per change, composes prompt previews, and talks to systemd for
the persona units. Secrets never leave the server: the UI only learns whether a key is SET.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

REPO = Path(__file__).resolve().parent.parent

PERSONA_UNITS = ("tiny-voice", "tiny-telegram", "tiny-thinker")   # the only units /api/personas may touch
RESTART_COOLDOWN_S = 30.0
# "is this key present" is all the UI learns; the value is never read into a response
SECRET_PRESENCE = ("OPENAI_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "AWS_ACCESS_KEY_ID", "AWS_PROFILE",
                   "TELEGRAM_BOT_TOKEN", "TINY_MCP_TOKEN")

_restart_lock = threading.Lock()
_last_restart: Dict[str, float] = {}


def _repo_modules():
    """tiny + tools.config from the repo root (the personas' own code), imported lazily like Ask does."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    import tiny  # noqa: PLC0415
    from tools import config  # noqa: PLC0415
    return tiny, config


def snapshot() -> Dict[str, Any]:
    """Everything the Settings sheet needs in one GET."""
    tiny, config = _repo_modules()
    personas = list(config.PERSONAS)
    values = config.get_all()
    env = {name: config.env_value(name) for name in config.SCHEMA}
    return {
        "schema": config.schema(),
        "values": values,                       # effective: DB -> env -> default
        "overrides": config.overrides(),        # what the owner changed (keys only matter)
        "env": env,                             # the bootstrap values a reset returns to
        "generations": config.generations(),
        "catalog": tiny.tool_catalog(),
        "defaults": {p: tiny.default_tool_names(p) for p in personas},
        "effective_tools": {p: tiny.effective_tool_names(p) for p in personas},
        "secrets": {name: bool(os.environ.get(name)) for name in SECRET_PRESENCE},
        "personas": personas,
        "prompt_personas": list(config.PROMPT_PERSONAS),
        "history": config.history(limit=20),
    }


def apply(values: Dict[str, Any], who: str, log: Callable[..., Any]) -> Dict[str, Any]:
    """Validate + store; one audit row per changed key (values truncated to 80 chars). ValueError on bad input."""
    _tiny, config = _repo_modules()
    if not isinstance(values, dict) or not values:
        raise ValueError("body must be a non-empty object of {key: value}")
    if len(values) > 100:
        raise ValueError("at most 100 keys per request")
    result = config.set_many(values, by=who)
    for key, diff in result["changed"].items():
        log("config", f"{key}: {diff['old']} -> {diff['new']}", who, key=key)
    result["values"] = config.get_all()
    result["overrides"] = config.overrides()
    return result


def reset(key: str, who: str, log: Callable[..., Any]) -> Dict[str, Any]:
    _tiny, config = _repo_modules()
    removed = config.reset(key, by=who)
    if removed:
        log("config", f"{key}: reset to env/default ({config._short(config.get(key))})", who, key=key)
    return {"ok": True, "removed": removed, "key": key, "value": config.get(key),
            "generations": config.generations(), "values": config.get_all(), "overrides": config.overrides()}


def preview(persona: str) -> Dict[str, Any]:
    """The composed system prompt + tool names the NEXT Agent of this persona would get (read-only)."""
    tiny, config = _repo_modules()
    if persona == "telegram":
        chat = str(config.get("telegram.default_chat_id") or "0")
        allowed = list(config.get("telegram.allowed_users") or [])
        prompt = tiny._telegram_prompt(chat, allowed[0] if allowed else "owner")
    elif persona == "thinker":
        prompt = tiny._thinker_prompt()
    elif persona == "voice":
        prompt = tiny._voice_prompt()
    elif persona in ("shell", "dashboard"):
        prompt = tiny._shell_prompt()
    else:
        raise ValueError(f"unknown persona {persona!r}; one of voice, telegram, thinker, shell, dashboard")
    try:
        from tools import tiny_mcp  # noqa: PLC0415
        prompt += tiny_mcp.prompt_block(persona)
    except Exception:  # noqa: BLE001
        pass
    tools = tiny.effective_tool_names(persona if persona != "shell" else "shell")
    return {"persona": persona, "prompt": prompt, "chars": len(prompt), "tools": tools,
            "model_id": tiny.model_id() if persona != "voice" else tiny.voice_settings()["model"] or "provider default",
            "note": config.get(f"agent.prompt_note.{persona}") if persona in config.PROMPT_PERSONAS else ""}


# ── persona units (systemd --user) ──────────────────────────────────────────
def _run(cmd: List[str], timeout: float = 5.0) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "") + (r.stderr or "")
    except Exception as e:  # noqa: BLE001
        return f"error: {e.__class__.__name__}"


def unit_status(unit: str) -> Dict[str, Any]:
    out = _run(["systemctl", "--user", "show", unit, "-p", "ActiveState,SubState,MainPID,ActiveEnterTimestamp,NRestarts"])
    props = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    journal = _run(["journalctl", "--user", "-b", f"_SYSTEMD_USER_UNIT={unit}.service", "-n", "3", "--no-pager", "-o", "cat"])
    lines = [ln[:200] for ln in journal.splitlines() if ln.strip()][-3:]
    try:
        pid: Optional[int] = int(props.get("MainPID", "0") or 0) or None
    except ValueError:
        pid = None
    last = _last_restart.get(unit)
    return {"unit": unit, "active": props.get("ActiveState", "unknown"), "sub": props.get("SubState", ""),
            "pid": pid, "since": props.get("ActiveEnterTimestamp", "") or None,
            "restarts": props.get("NRestarts"), "journal": lines,
            "cooldown_s": max(0, int(RESTART_COOLDOWN_S - (time.monotonic() - last))) if last else 0}


def personas() -> Dict[str, Any]:
    return {"units": [unit_status(u) for u in PERSONA_UNITS], "t": time.time()}


def restart(unit: str, who: str, log: Callable[..., Any]) -> Dict[str, Any]:
    """systemctl --user restart <unit> — allow-listed units only, one restart per unit per 30 s."""
    if unit not in PERSONA_UNITS:
        raise ValueError(f"unit must be one of {', '.join(PERSONA_UNITS)}")
    with _restart_lock:
        last = _last_restart.get(unit)
        if last is not None and time.monotonic() - last < RESTART_COOLDOWN_S:
            raise PermissionError(f"{unit} was restarted {int(time.monotonic() - last)} s ago; wait "
                                  f"{int(RESTART_COOLDOWN_S - (time.monotonic() - last))} s")
        _last_restart[unit] = time.monotonic()
    try:
        subprocess.run(["systemctl", "--user", "restart", unit], capture_output=True, text=True, timeout=30, check=True)
    except Exception as e:  # noqa: BLE001
        log("error", f"restart {unit} failed: {str(e)[:200]}", who)
        raise RuntimeError(f"systemctl --user restart {unit} failed: {e}") from e
    log("control", f"restarted {unit}", who)
    return {"ok": True, **unit_status(unit)}
