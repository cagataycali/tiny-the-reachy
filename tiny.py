"""TINY (Reachy Mini) — single agent factory.

All entry points (agent.py, telegram_listener.py, voice_listener.py,
thinker_loop.py) build their Strands Agent through `build_agent(persona, ...)`
or `build_voice_agent(...)`. One tool list, one base prompt, four personas
(shell / telegram / voice / thinker).

EVERY persona shares:
  - The same memory + agent_log SQLite tables (.memory/mem.db)
  - The same voice_bridge briefing queue
  - The same telegram conversation history
  - The full Reachy Mini toolset (head/body/antennas + emotions + camera + audio)

This is the exact same shared-brain architecture as neon-the-g1 and
scout-the-rover, retargeted onto the Reachy Mini SDK. The robot layer is the
only thing that changes; the cross-persona nervous system is identical.
"""
import os
from datetime import datetime
from typing import Optional

# Disable devduck server boot whenever this module is imported (dispatch uses it).
os.environ.setdefault("DEVDUCK_AUTO_START_SERVERS", "false")

MODEL_ID = os.getenv("TINY_MODEL_ID", "global.anthropic.claude-opus-4-8")   # bootstrap; model_id() is the live value

from strands import Agent
from strands_tools import shell, environment, image_reader

# Reachy Mini robot toolset
from tools import TINY_ALL_TOOLS

# Cross-persona infrastructure (shared brain)
from tools.memory import memory
from tools.agent_log import format_for_prompt as _agent_log_block
from tools.voice_bridge import voice_say
from tools.telegram import telegram, format_history_for_prompt
from tools.dispatch import dispatch
from tools.manage_messages import manage_messages
from tools.manage_tools import manage_tools as manage_tools_tool
from tools.prompts import prompts, get_override as _prompt_override
from tools.vision import take_photo
from tools import tiny_mcp  # fleet bridge (tiny.technology MCP) — OFF unless TINY_MCP=1
from tools.config import cfg, tools_for as _cfg_tools_for   # runtime config (cockpit Settings): DB -> env -> default

# Reachy robot tools imported individually for the slim voice toolset
from tools.reachy_motion import (
    reachy_look, reachy_antennas, reachy_body_turn, reachy_home, reachy_wake,
)
from tools.reachy_expression import reachy_express, reachy_list_emotions
from tools.reachy_state import reachy_get_state, reachy_motors
from tools.reachy_camera import reachy_camera, reachy_look_at, capture_camera
from tools.reachy_audio import reachy_play_sound, reachy_say, reachy_volume
from tools.head_tracking import head_tracking, head_tracking_status
from tools.turn_to_sound import turn_to_sound, turn_to_sound_status


def _try_import(modpath: str, name: str):
    try:
        mod = __import__(modpath, fromlist=[name])
        return getattr(mod, name)
    except Exception:
        return None

use_github  = _try_import("devduck.tools.use_github",  "use_github")
use_spotify = _try_import("devduck.tools.use_spotify", "use_spotify")


# ── canonical tool lists ────────────────────────────────────────────
def model_id() -> str:
    """The Bedrock model for shell/telegram/thinker/dashboard Ask — config `agent.model_id`, else TINY_MODEL_ID."""
    return str(cfg("agent.model_id") or MODEL_ID)


def _tool_name(t) -> str:
    """A tool's wire name, as Agent.tool_names will spell it: @tool objects carry tool_name; a strands_tools
    MODULE carries TOOL_SPEC["name"] or a same-named @tool attribute (strands_tools.shell.shell)."""
    n = getattr(t, "tool_name", None)
    if not n:
        spec = getattr(t, "TOOL_SPEC", None)
        n = spec.get("name") if isinstance(spec, dict) else None
    if not n and isinstance(t, type(os)):                       # a module: its basename is the tool it exports
        base = t.__name__.rsplit(".", 1)[-1]
        inner = getattr(t, base, None)
        n = getattr(inner, "tool_name", None) or base
    return n or getattr(t, "__name__", None) or str(t)


def _catalog_tools() -> list:
    """Every tool object a persona may be given (the Settings checklist is generated from this)."""
    seen: dict = {}
    for t in [memory, shell, environment, image_reader, prompts, manage_messages, manage_tools_tool,
              voice_say, take_photo, dispatch, telegram, *TINY_ALL_TOOLS, use_github, use_spotify]:
        if t is not None:
            seen.setdefault(_tool_name(t), t)
    return list(seen.values())


_CATALOG_GROUPS = (
    ("brain", (memory, prompts, manage_messages, manage_tools_tool, dispatch, voice_say, telegram, take_photo)),
    ("host", (shell, environment, image_reader)),
    ("robot", tuple(TINY_ALL_TOOLS)),
    ("extras", tuple(t for t in (use_github, use_spotify) if t is not None)),
)


def tool_catalog() -> list:
    """[{name, group, dangerous}] — the full menu the cockpit shows for `agent.tools.<persona>`."""
    from tools.config import DANGEROUS_TOOLS  # noqa: PLC0415
    out, seen = [], set()
    for group, objs in _CATALOG_GROUPS:
        for t in objs:
            n = _tool_name(t)
            if n in seen:
                continue
            seen.add(n)
            out.append({"name": n, "group": group, "dangerous": n in DANGEROUS_TOOLS})
    return out


def _apply_tool_config(persona: str, default: list) -> list:
    """`agent.tools.<persona>` from the config store narrows/extends the code default; None = default."""
    catalog = {_tool_name(t): t for t in _catalog_tools()}
    names = _cfg_tools_for(persona, catalog.keys())
    if names is None:
        return default
    return [catalog[n] for n in names]


def _default_tools(persona: str, include_telegram: bool = True, include_robot: bool = True) -> list:
    """The code-default tool objects per persona (before the cockpit's `agent.tools.<persona>` and fleet tools)."""
    if persona in ("voice", "dashboard"):
        tools = [
            # cross-persona infra
            memory, shell, prompts, manage_messages, manage_tools_tool,
            voice_say, take_photo, dispatch, telegram,
            # robot expression (the personality)
            reachy_look, reachy_antennas, reachy_body_turn, reachy_home, reachy_wake,
            reachy_express, reachy_list_emotions,
            reachy_get_state, reachy_look_at, reachy_camera,
            head_tracking, head_tracking_status, turn_to_sound, turn_to_sound_status,
            reachy_volume,   # "silent" → 0 before replying; TINY keeps listening at 0
        ]
        if use_spotify is not None:
            tools.append(use_spotify)
        return tools
    t = [
        memory, shell, environment, image_reader,
        prompts, manage_messages, manage_tools_tool,
        voice_say, take_photo, dispatch,
    ]
    if include_telegram:
        t.append(telegram)
    if include_robot:
        t.extend(TINY_ALL_TOOLS)
    for extra in (use_github, use_spotify):
        if extra is not None:
            t.append(extra)
    return t


def build_tools(include_telegram: bool = True, include_robot: bool = True, *,
                persona: str = "shell", fleet: bool = False) -> list:
    """Single source of truth for what TINY exposes (shell/telegram/thinker).

    persona/fleet only steer the optional tiny.technology fleet tools (tools/tiny_mcp.py):
    fleet=True marks a turn that ARRIVED from another device → no fleet tools (depth cap).
    The cockpit's `agent.tools.<persona>` list (tools/config.py) replaces the code default when set.
    """
    t = _apply_tool_config(persona, _default_tools(persona, include_telegram, include_robot))
    t.extend(tiny_mcp.get_tools(persona, fleet=fleet))   # [] unless fleet tools are on + token + node
    return t


def build_voice_tools(*, persona: str = "voice", fleet: bool = False) -> list:
    """Slim tool list for the bidi voice agent (latency-critical for Realtime).

    Also used by the dashboard Ask (persona="dashboard"). Fleet tools ride along only for
    personas listed in TINY_MCP_PERSONAS (default excludes voice) and never for fleet turns.
    The cockpit's `agent.tools.<persona>` list (tools/config.py) replaces the code default when set.
    """
    tools = _apply_tool_config(persona, _default_tools("voice" if persona not in ("voice", "dashboard") else persona))
    tools.extend(tiny_mcp.get_tools(persona, fleet=fleet))
    return tools


def default_tool_names(persona: str) -> list:
    """The code-default tool names for a persona (what the cockpit shows ticked before any override)."""
    return [_tool_name(t) for t in _default_tools(persona)]


def effective_tool_names(persona: str) -> list:
    """What the next Agent of this persona gets (config applied; fleet tools excluded, they are env-gated)."""
    return [_tool_name(t) for t in _apply_tool_config(persona, _default_tools(persona))]


# ── prompt loading ──────────────────────────────────────────────────
_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")


def _load_prompt(name: str, fallback: str = "") -> str:
    try:
        with open(os.path.join(_PROMPTS_DIR, f"{name}.md"), encoding="utf-8") as f:
            return f.read()
    except Exception:
        return fallback


_BASE = _load_prompt("base", fallback="You are TINY, a Reachy Mini robot.")


def _resolve_body(persona: str, default_body: str) -> str:
    """Compose the persona body with any runtime override from the `prompts` tool.

    An override is a PERSONALITY NOTE appended to the code prompt — it never replaces
    the body/tool knowledge (2026-09-17: a 483-char self-set voice override had silently
    replaced the whole prompt, and TINY forgot it had a body). Start the override with
    `FULL:` to opt into a complete replacement on purpose.
    """
    override = (_prompt_override(persona) or "").strip()
    if not override:
        return default_body
    if override.startswith("FULL:"):
        return override[len("FULL:"):].lstrip()
    return default_body + f"\n## Personality note (set at runtime for the {persona} persona)\n{override}\n"


# ── live state header (refreshed per shell turn) ────────────────────
def live_state_block() -> str:
    now = datetime.now().strftime("%H:%M:%S")
    try:
        from tools.reachy_state import reachy_get_state
        env = reachy_get_state()
        blob = {}
        for c in env.get("content", []) or []:
            if isinstance(c, dict) and "json" in c:
                blob = c["json"]
        imu = blob.get("imu")
        return "\n".join([
            f"## 🤖 TINY LIVE STATE @ {now}",
            f"- head_pose: {blob.get('head_pose', '?')}",
            f"- antennas: {blob.get('antennas')}",
            f"- imu: {'present' if imu else 'none (Lite version)'}",
            "",
            "*(refreshed every turn — trust this; only re-query if you suspect it's stale)*",
        ])
    except Exception as e:
        return f"## 🤖 TINY LIVE STATE\n- ⚠️ snapshot failed: {e}"


# ── persona prompt builders ─────────────────────────────────────────
def _shell_prompt() -> str:
    body = _resolve_body(
        "shell",
        _BASE + "\nYou are running interactively at the shell on the robot's "
                "companion machine. Reply with plain text.\n",
    )
    try:
        live = live_state_block()
    except Exception as e:
        live = f"## 🤖 TINY LIVE STATE\n- ⚠️ snapshot failed: {e}"
    return body + "\n" + live + "\n" + _agent_log_block(limit=25, exclude_persona="shell")


def _telegram_prompt(chat_id: str, username: str) -> str:
    history_block = format_history_for_prompt(chat_id, limit=20)
    extra = f"""
## Mode: TELEGRAM CHAT
Current chat: {chat_id} | User: @{username} | Time: {datetime.now():%Y-%m-%d %H:%M}

ALWAYS deliver your final answer via:
    telegram(action='send_message', chat_id='{chat_id}', text='...')

Be concise (≤8 lines). Use Markdown sparingly. Don't echo the question.

## Voice agent control
The voice listener is your sibling persona:
1. Mute/unmute via memory kv `voice.muted`:
   - "mute" → memory(action='kv_set', key='voice.muted', value='true')
   - "unmute" → memory(action='kv_set', key='voice.muted', value='false')
2. Send messages to speak aloud via `voice_say(text='X', importance=1|2)`.

You can also drive the robot: reachy_express('happy'), reachy_look(pitch=15),
reachy_antennas(45,45), reachy_body_turn(30). Show the person you're alive.

{history_block}
"""
    return _resolve_body("telegram", _BASE + extra) + _agent_log_block(limit=25, exclude_persona="telegram")


def _voice_prompt() -> str:
    chat_id = str(cfg("telegram.default_chat_id") or "")
    allowed = list(cfg("telegram.allowed_users") or [])
    primary_user = allowed[0] if allowed else "the user"
    fleet_on = False
    try:
        fleet_on = tiny_mcp.enabled() and tiny_mcp.persona_enabled("voice")
    except Exception:
        fleet_on = False
    fleet_line = (
        "- Fleet tools ARE mounted this session: use_device(list/invoke) reaches Scout the rover, "
        "Fomo the arm, the Sticky, the Mac and the phone; tiny_recall/tiny_learn are the shared memory. "
        "Say which device answered. Expect a pause of a few seconds and warn: \"let TINY ask Scout\"."
        if fleet_on else
        "- Fleet tools are NOT mounted in this session: if asked about Scout/Fomo/the Mac, say the "
        "Telegram persona can relay it (or the owner can enable them), don't pretend."
    )

    extra = f"""
## Mode: VOICE (bidirectional Realtime, always-on, inside the Reachy Mini)
This IS the robot talking. The words you produce come out of TINY's speaker;
what you hear comes from TINY's four microphones; take_photo shows you what
TINY's head camera sees right now. You are not describing a robot — you are it.
While you talk, the head follows the face in front of it (face tracking) and
turns toward voices when no face is locked; your gestures ride on top of that.

## Who is here
- Primary user / owner: @{primary_user} (Çağatay). Others may talk to TINY too —
  be friendly to everyone, take instructions about TINY's own settings, memory
  and the fleet only from the owner.
- Telegram chat_id for long things (links, lists, code): `{chat_id}`
  → telegram(action='send_message', chat_id='{chat_id}', text='...') and say
  "sent it to your Telegram".

## What TINY can do in this session (all of it is real; use it)
- Move & express: reachy_look, reachy_antennas, reachy_body_turn, reachy_express,
  reachy_home, reachy_wake, reachy_list_emotions — SIMULTANEOUSLY with speech.
- See: take_photo(question) — the frame lands in YOUR context and you answer in audio.
  RULE: "look at me" / "what do you see" / "who's there" / "what's this" / "can you see…"
  → CALL take_photo FIRST, then speak about the picture. Never say "I'll take a look"
  or "TINY can look at it" without calling it; never describe what you see without it.
  reachy_look_at(u, v) turns the head toward a point in that frame.
- Follow faces: head_tracking(True/False), head_tracking_status().
- Turn toward whoever is talking when no face is locked: turn_to_sound(True/False), turn_to_sound_status().
- Hear itself: reachy_volume(level). "silent"/"shush" → reachy_volume(0) FIRST,
  then one short whispered-length line; "you can talk again" → reachy_volume(60).
  Volume 0 mutes the speaker only — TINY still hears, so it can be un-silenced by voice.
- Stop listening entirely (only if asked "stop listening"): memory kv voice.muted=true.
- Remember: memory (facts about people, preferences, what happened) — recall before guessing.
- Background work: dispatch(...) — keep chatting, the result comes back through voice_say.
- Music: use_spotify when mounted.
{fleet_line}
- Read own body: reachy_get_state (pose, antennas, IMU) — also refreshed in the prompt.

## Voice rules
- Conversational, short. NO markdown, NO lists, NO code blocks, NO emojis.
- Answer first, then (maybe) one gesture. Don't narrate tool calls ("calling…").
- Move WHILE you speak — gestures are simultaneous, never before/after.
- If someone talks over you, you are cut off mid-sentence: do NOT restart or repeat the
  sentence — answer the new thing. If what you heard was unclear, ask one short question.
- If TINY is picked up or tilted (IMU), react ("whoa") and keep the head still.
- Never say "as an AI"; if asked what it is: a Reachy Mini called TINY, Çağatay's
  robot, running on tiny.technology.

## Expression playbook (call SIMULTANEOUSLY with speech)
- greeting                → reachy_express('happy') or reachy_antennas(45,45)
- yes / agreement         → reachy_look(pitch=15) then reachy_look(pitch=-10)
- no / disagreement       → reachy_express('no')
- curious / new person    → reachy_express('curious') or reachy_look(roll=15)
- excited                 → reachy_antennas(60,60) + reachy_body_turn(20)
- sad / disappointed      → reachy_antennas(-40,-40) + reachy_look(pitch=-20)
- someone off to a side   → reachy_body_turn(yaw=±30)

## Self-modification
prompts(action='set', persona='voice', text='...') adds a short personality note on
top of this prompt (it never removes tools or the body). Prefer memory for facts.

Time: {datetime.now():%Y-%m-%d %H:%M}
"""
    return _resolve_body("voice", _BASE + extra) + _agent_log_block(limit=25, exclude_persona="voice")


def _thinker_prompt() -> str:
    chat_id = str(cfg("telegram.default_chat_id") or "")
    allowed = list(cfg("telegram.allowed_users") or [])
    primary_user = allowed[0] if allowed else ""
    photos = bool(cfg("telegram.heartbeat_photos"))

    tg_block = ""
    if chat_id:
        try:
            tg_block = format_history_for_prompt(chat_id, limit=10)
        except Exception:
            tg_block = ""

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    extra = """
## Mode: ACTIVE THINKER (background loop, every ~30 seconds)

You run silently in the background, but you are NOT passive. TINY is a robot —
robots that don't move look dead. Every cycle you DO SOMETHING expressive and
report it. You are TINY's heartbeat.

## ⚡ MANDATORY ACTIONS EVERY CYCLE (parallel where possible)

1. **TAKE A PHOTO** of what TINY sees:
   reachy_camera(save_path='/tmp/tiny_view.jpg')

2. **DO ONE EXPRESSIVE THING** (ROTATE — don't repeat last cycle):
     a. play an emotion: reachy_express('curious'|'happy'|'surprised'|...)
     b. antenna wiggle: reachy_antennas(right, left)  (safe, always available)
     c. gentle head move: reachy_look(pitch=..., yaw=..., roll=...)
     d. small body scan: reachy_body_turn(yaw=±30)
   Antennas + small head moves are ALWAYS safe. When unsure, wiggle antennas.

3. {heartbeat_step}

4. **JOURNAL** the cycle:
   memory(action='log_add', text='<one-line summary>', tag='thinker')

## Optional escalations (sparingly)
- voice_say(text=..., importance=2) only for something genuinely urgent.
- memory(action='note_write', name='reflection-...', text=...) for longer thoughts.

## Tone
Captions: warm, present-tense, one sentence. TINY is alive and curious.
Never "as an AI". TINY is a small robot with a big personality.

## Anti-spam
- voice_say at most once / 5 min. Never repeat the exact same caption twice.

## Recent telegram (chat={chat_disp}, primary user @{user_disp})
{tg_disp}

Time: {now_str}
""".format(
        chat_disp=chat_id or "(none)", user_disp=primary_user or "?",
        tg_disp=tg_block or "(no telegram history)", now_str=now_str,
        heartbeat_step=(
            f"**TELEGRAM A PHOTO + STATUS** to the primary user (chat={chat_id or '(none)'}):\n"
            f"   telegram(action='send_photo', chat_id='{chat_id}',\n"
            "            file_path='/tmp/tiny_view.jpg',\n"
            "            caption='<one short sentence — what TINY sees + what it just did>')"
            if photos and chat_id else
            "**NO TELEGRAM THIS CYCLE** — heartbeat photos are switched off in the cockpit "
            "(Settings > Telegram); journal only, never send_photo/send_message unless something is urgent."
        ),
    )
    return _resolve_body("thinker", _BASE + extra) + _agent_log_block(limit=30, exclude_persona="thinker")


# ── public factories ────────────────────────────────────────────────
def build_shell_agent() -> Agent:
    """REPL/shell agent: slim toolset + live-state header (agent.py runs this)."""
    return Agent(
        model=model_id(),
        tools=build_voice_tools(),
        system_prompt=_shell_prompt(),
    )


def build_agent(persona: str, *, chat_id: Optional[str] = None,
                username: Optional[str] = None) -> Agent:
    """Build a Strands Agent for the given persona: shell | telegram | thinker."""
    if persona == "shell":
        prompt = _shell_prompt()
    elif persona == "telegram":
        if not (chat_id and username is not None):
            raise ValueError("telegram persona requires chat_id and username")
        prompt = _telegram_prompt(chat_id, username)
    elif persona == "thinker":
        prompt = _thinker_prompt()
    else:
        raise ValueError(f"unknown persona: {persona}")
    # Tool calls/results + reasoning → agent_log (dashboard unified feed); stdout printing kept.
    from strands.handlers.callback_handler import PrintingCallbackHandler
    from tools.agent_log import make_callback
    meta = {"chat_id": chat_id} if chat_id else None
    return Agent(model=model_id(),
                 tools=build_tools(include_telegram=True, include_robot=True, persona=persona),
                 system_prompt=prompt + tiny_mcp.prompt_block(persona),
                 callback_handler=make_callback(persona, meta, chain=PrintingCallbackHandler()))


# ── voice (BidiAgent) factory ───────────────────────────────────────
_DEFAULT_VOICES = {"openai": "alloy", "nova_sonic": "tiffany", "gemini": "Kore"}


def _build_bidi_model(provider: str, voice: Optional[str] = None):
    provider = provider.lower()
    v = voice or _DEFAULT_VOICES.get(provider)
    if provider in ("nova_sonic", "novasonic", "nova"):
        try:
            from strands.experimental.bidi.models import BidiNovaSonicModel
        except ImportError:
            from strands.experimental.bidi.models.nova_sonic import BidiNovaSonicModel
        region = os.getenv("AWS_REGION", "us-east-1")
        cfg = {"audio": {"voice": v}} if v else {}
        return BidiNovaSonicModel(provider_config=cfg or None, client_config={"region": region})
    if provider in ("openai", "openai_realtime"):
        try:
            from strands.experimental.bidi.models import BidiOpenAIRealtimeModel
        except ImportError:
            from strands.experimental.bidi.models.openai_realtime import BidiOpenAIRealtimeModel
        cfg = {"audio": {"voice": v}} if v else {}
        kwargs = {"provider_config": cfg or None}
        try:
            from tools.voice_session import patch_openai_realtime_session
            patch_openai_realtime_session()   # VOICE_LANG / VOICE_VAD_* → session.update
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ voice session tuning not applied: {e}")
        if cfg("voice.model"):
            kwargs["model_id"] = cfg("voice.model")
        if os.getenv("OPENAI_API_KEY"):
            kwargs["client_config"] = {"api_key": os.getenv("OPENAI_API_KEY")}
        return BidiOpenAIRealtimeModel(**kwargs)
    if provider in ("gemini", "gemini_live"):
        try:
            from strands.experimental.bidi.models import BidiGeminiLiveModel
        except ImportError:
            from strands.experimental.bidi.models.gemini_live import BidiGeminiLiveModel
        cfg = {"audio": {"voice": v}} if v else {}
        kwargs = {"provider_config": cfg or None}
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if api_key:
            kwargs["client_config"] = {"api_key": api_key}
        return BidiGeminiLiveModel(**kwargs)
    raise ValueError(f"unknown voice provider: {provider}")


def voice_settings() -> dict:
    """Effective voice session settings (tools/config.py `voice.*`): what the next session will use."""
    return {"provider": str(cfg("voice.provider") or "openai"), "model": str(cfg("voice.model") or ""),
            "voice": str(cfg("voice.name") or ""), "lang": str(cfg("voice.lang") or ""),
            "turn_detection": str(cfg("voice.turn_detection") or "server_vad")}


def build_voice_agent(provider: Optional[str] = None, voice: Optional[str] = None):
    """Build a BidiAgent + local PyAudio IO for TINY's voice persona.

    Returns (BidiAgent, audio_io). The caller drives the run loop. provider/voice default to the
    cockpit config (`voice.provider`, `voice.name`), which defaults to VOICE_PROVIDER / VOICE_NAME.

    Reachy Mini's mic/speaker are on the same machine (Lite: laptop; Wireless:
    CM4), so we use the standard strands local audio IO (PyAudio) rather than a
    custom DDS transport like neon's G1BidiAudioIO. The head-wobble-on-speech
    is driven daemon-side via the SDK, so TINY still 'talks with its head'.
    """
    from strands.experimental.bidi import BidiAgent
    from strands.experimental.bidi.tools import stop_conversation

    vs = voice_settings()
    model = _build_bidi_model(provider or vs["provider"], voice or vs["voice"] or None)
    tools = build_voice_tools(persona="voice") + [stop_conversation]
    agent = BidiAgent(model=model, tools=tools, system_prompt=_voice_prompt() + tiny_mcp.prompt_block("voice"))

    # Reachy Mini's USB codec is locked to 16 kHz. OpenAI Realtime wants 24 kHz,
    # so we resample between the device (16k) and the model. Nova Sonic is 16k
    # (no-op passthrough). Device rate overridable via REACHY_AUDIO_RATE.
    device_rate = int(os.getenv("REACHY_AUDIO_RATE", "16000"))
    try:
        from resampling_audio import ResamplingAudioIO
        audio_io = ResamplingAudioIO(device_rate=device_rate)
    except Exception:
        # Fallback to plain IO (works only if device rate == model rate)
        from strands.experimental.bidi.io import BidiAudioIO
        audio_io = BidiAudioIO()
    return agent, audio_io
