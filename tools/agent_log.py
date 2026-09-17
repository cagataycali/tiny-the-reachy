"""Unified cross-persona reasoning log.

ALL four personas (shell, thinker, telegram, voice) write here and read from
here. The log is injected into every system prompt so each persona knows what
the others have been doing.

Schema:
  agent_log(id, persona, role, text, meta_json, ts)
    persona  : shell | thinker | telegram | voice
    role     : user | assistant | system | tool
    text     : the message body
    meta     : optional JSON (chat_id, repo, tool_name, …)

Trimming rule: we keep the last N rows in `format_for_prompt()` so prompts stay
bounded. Old rows live forever in the DB for analytics — no auto-deletion.
"""
import json
import sqlite3
from pathlib import Path
from typing import Optional

DB = Path(__file__).resolve().parent.parent / ".memory" / "mem.db"
DEFAULT_LIMIT = 30
MAX_TEXT = 600       # truncate per-message text in prompt block


def _conn():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=5)
    c.execute("""
        CREATE TABLE IF NOT EXISTS agent_log(
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            persona TEXT NOT NULL,
            role    TEXT NOT NULL,
            text    TEXT NOT NULL,
            meta    TEXT,
            ts      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_alog_ts ON agent_log(id DESC)")
    c.commit()
    return c


def record(persona: str, role: str, text: str, meta: Optional[dict] = None) -> int:
    """Append a single turn to the unified log."""
    if not text:
        return 0
    c = _conn()
    cur = c.execute(
        "INSERT INTO agent_log(persona, role, text, meta) VALUES(?,?,?,?)",
        (persona, role, str(text)[:8000], json.dumps(meta) if meta else None),
    )
    c.commit()
    rid = cur.lastrowid
    c.close()
    return rid


def recent(limit: int = DEFAULT_LIMIT, persona: Optional[str] = None) -> list:
    """Last N rows, oldest-first."""
    c = _conn()
    if persona:
        rows = c.execute(
            "SELECT persona, role, text, meta, ts FROM agent_log "
            "WHERE persona=? ORDER BY id DESC LIMIT ?",
            (persona, limit),
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT persona, role, text, meta, ts FROM agent_log "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    c.close()
    rows.reverse()
    return [
        {"persona": p, "role": r, "text": t,
         "meta": json.loads(m) if m else None, "ts": ts}
        for p, r, t, m, ts in rows
    ]


def format_for_prompt(limit: int = DEFAULT_LIMIT,
                       exclude_persona: Optional[str] = None) -> str:
    """Format unified log as a system-prompt context block.

    Excluding the current persona's own rows (`exclude_persona`) avoids
    feeding the agent its own past output as if it were context — the
    agent already has its own conversation memory for that. The point is
    cross-persona awareness.
    """
    rows = recent(limit)
    if exclude_persona:
        rows = [r for r in rows if r["persona"] != exclude_persona]
    if not rows:
        return ""
    lines = [f"\n## 🧠 Unified Reasoning Log (last {len(rows)} cross-persona turns):"]
    for r in rows:
        persona = r["persona"]
        role = r["role"]
        text = r["text"][:MAX_TEXT]
        if len(r["text"]) > MAX_TEXT:
            text += "…"
        meta = r["meta"] or {}
        meta_bits = []
        if "chat_id" in meta: meta_bits.append(f"chat={meta['chat_id']}")
        if "repo" in meta:    meta_bits.append(f"repo={meta['repo']}")
        if "tool" in meta:    meta_bits.append(f"tool={meta['tool']}")
        meta_str = f" ({', '.join(meta_bits)})" if meta_bits else ""
        lines.append(f"[{r['ts']}] [{persona}/{role}]{meta_str}: {text}")
    return "\n".join(lines) + "\n"


def prune(keep_last_n: int = 10000) -> int:
    """Keep the last ``keep_last_n`` rows; delete older. Returns deleted rowcount."""
    c = _conn()
    n = c.execute(
        "DELETE FROM agent_log WHERE id NOT IN "
        "(SELECT id FROM agent_log ORDER BY id DESC LIMIT ?)",
        (keep_last_n,),
    ).rowcount
    c.commit()
    c.close()
    return n


def stats() -> dict:
    c = _conn()
    by_persona = c.execute(
        "SELECT persona, COUNT(*) FROM agent_log GROUP BY persona ORDER BY 2 DESC"
    ).fetchall()
    total = c.execute("SELECT COUNT(*) FROM agent_log").fetchone()[0]
    c.close()
    return {"total": total, "by_persona": dict(by_persona)}


def clear(persona: Optional[str] = None) -> int:
    c = _conn()
    if persona:
        n = c.execute("DELETE FROM agent_log WHERE persona=?", (persona,)).rowcount
    else:
        n = c.execute("DELETE FROM agent_log").rowcount
    c.commit()
    c.close()
    return n


# ── live capture helpers (dashboard unified feed) ───────────────────────────────
# Every persona already records its user/assistant turns. These add the REST of the
# reasoning trace — tool calls, tool results, reasoning text, voice transcripts — as
# extra rows so the dashboard timeline can show one feed across personas.
#   role "tool"      text "<name> <input json>"      meta {tool, tool_use_id, phase:"use"}
#   role "tool"      text "<result text>"            meta {tool, tool_use_id, phase:"result", status}
#   role "reasoning" text "<reasoning text>"         meta {}
TOOL_TEXT_MAX = 1500


def _content_blocks(message) -> list:
    try:
        c = message.get("content") if isinstance(message, dict) else None
        return c if isinstance(c, list) else []
    except Exception:
        return []


def record_message(persona: str, message, meta: Optional[dict] = None, names: Optional[dict] = None) -> None:
    """Record the tool/reasoning parts of a Strands Message (dict with role + content blocks).

    `names` maps toolUseId → tool name so results can be labelled (kept by the caller)."""
    names = names if names is not None else {}
    base = dict(meta or {})
    for block in _content_blocks(message):
        if not isinstance(block, dict):
            continue
        if "toolUse" in block:
            tu = block["toolUse"] or {}
            name, tid = tu.get("name", "?"), tu.get("toolUseId", "")
            names[tid] = name
            try:
                inp = json.dumps(tu.get("input", {}), ensure_ascii=False)
            except Exception:
                inp = str(tu.get("input", ""))
            record(persona, "tool", f"{name} {inp}"[:TOOL_TEXT_MAX],
                   {**base, "tool": name, "tool_use_id": tid, "phase": "use"})
        elif "toolResult" in block:
            tr = block["toolResult"] or {}
            tid = tr.get("toolUseId", "")
            parts = []
            for c in tr.get("content", []) or []:
                if isinstance(c, dict):
                    if "text" in c:
                        parts.append(str(c["text"]))
                    elif "json" in c:
                        try:
                            parts.append(json.dumps(c["json"], ensure_ascii=False))
                        except Exception:
                            parts.append(str(c["json"]))
                    elif "image" in c:
                        parts.append("[image]")
            text = " ".join(parts).strip() or f"[{tr.get('status', 'ok')}]"
            record(persona, "tool", text[:TOOL_TEXT_MAX],
                   {**base, "tool": names.get(tid, "?"), "tool_use_id": tid, "phase": "result",
                    "status": tr.get("status", "success")})
        elif "reasoningContent" in block:
            rc = block["reasoningContent"] or {}
            txt = (rc.get("reasoningText") or {}).get("text") if isinstance(rc, dict) else None
            if txt:
                record(persona, "reasoning", str(txt)[:TOOL_TEXT_MAX], base or None)


def make_callback(persona: str, meta: Optional[dict] = None, chain=None):
    """A Strands `callback_handler` that records tool use/results + reasoning to agent_log.

    Text deltas are NOT recorded here (the persona records its final assistant text itself).
    `chain` (e.g. the default PrintingCallbackHandler) still receives every event."""
    names: dict = {}

    def cb(**kw):
        if chain is not None:
            try:
                chain(**kw)
            except Exception:
                pass
        msg = kw.get("message")
        if msg:
            try:
                record_message(persona, msg, meta, names)
            except Exception:
                pass
    return cb


class BidiTranscriptSink:
    """`BidiOutput` for a BidiAgent: records FINAL transcripts (user speech → role user,
    model speech → role assistant) and tool calls (from the agent's own message hook)."""

    def __init__(self, persona: str = "voice", meta: Optional[dict] = None):
        self.persona, self.meta = persona, meta
        self._names: dict = {}
        self._partial: dict = {}          # role → accumulated partial transcript (fallback when no final arrives)

    async def start(self, agent) -> None:
        # tool use / result rows via the message hook (covers every provider)
        try:
            from strands.experimental.bidi.hooks.events import BidiMessageAddedEvent
            agent.hooks.add_callback(BidiMessageAddedEvent, self._on_message)
        except Exception:
            pass
        record(self.persona, "system", "voice session started", self.meta)

    async def stop(self) -> None:
        record(self.persona, "system", "voice session stopped", self.meta)

    def _on_message(self, event) -> None:
        try:
            record_message(self.persona, event.message, self.meta, self._names)
        except Exception:
            pass

    async def __call__(self, event) -> None:
        try:
            t = event.get("type") if isinstance(event, dict) else None
            if t == "bidi_transcript_stream":
                role = str(event.get("role", "assistant"))
                if event.get("is_final"):
                    text = (event.get("current_transcript") or event.get("text") or self._partial.pop(role, "")).strip()
                    self._partial.pop(role, None)
                    if text:
                        record(self.persona, "user" if role == "user" else "assistant", text, self.meta)
                else:
                    self._partial[role] = self._partial.get(role, "") + str(event.get("text") or "")
            elif t == "bidi_response_complete":
                # some providers stream assistant deltas without a final → flush what we have
                text = self._partial.pop("assistant", "").strip()
                if text:
                    record(self.persona, "assistant", text, self.meta)
            elif t == "bidi_interruption":
                self._partial.pop("assistant", None)
            elif t == "bidi_error":
                record(self.persona, "system", f"voice error: {str(event.get('error') or event)[:300]}", self.meta)
        except Exception:
            pass
