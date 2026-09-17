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

MODEL_ID = os.getenv("TINY_MODEL_ID", "global.anthropic.claude-opus-4-8")

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

# Reachy robot tools imported individually for the slim voice toolset
from tools.reachy_motion import (
    reachy_look, reachy_antennas, reachy_body_turn, reachy_home, reachy_wake,
)
from tools.reachy_expression import reachy_express, reachy_list_emotions
from tools.reachy_state import reachy_get_state, reachy_motors
from tools.reachy_camera import reachy_camera, reachy_look_at, capture_camera
from tools.reachy_audio import reachy_play_sound, reachy_say, reachy_volume
from tools.head_tracking import head_tracking, head_tracking_status


def _try_import(modpath: str, name: str):
    try:
        mod = __import__(modpath, fromlist=[name])
        return getattr(mod, name)
    except Exception:
        return None

use_github  = _try_import("devduck.tools.use_github",  "use_github")
use_spotify = _try_import("devduck.tools.use_spotify", "use_spotify")


# ── canonical tool lists ────────────────────────────────────────────
def build_tools(include_telegram: bool = True, include_robot: bool = True, *,
                persona: str = "shell", fleet: bool = False) -> list:
    """Single source of truth for what TINY exposes (shell/telegram/thinker).

    persona/fleet only steer the optional tiny.technology fleet tools (tools/tiny_mcp.py):
    fleet=True marks a turn that ARRIVED from another device → no fleet tools (depth cap).
    """
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
    t.extend(tiny_mcp.get_tools(persona, fleet=fleet))   # [] unless TINY_MCP=1 + token + node
    return t


def build_voice_tools(*, persona: str = "voice", fleet: bool = False) -> list:
    """Slim tool list for the bidi voice agent (latency-critical for Realtime).

    Also used by the dashboard Ask (persona="dashboard"). Fleet tools ride along only for
    personas listed in TINY_MCP_PERSONAS (default excludes voice) and never for fleet turns.
    """
    tools = [
        # cross-persona infra
        memory, shell, prompts, manage_messages, manage_tools_tool,
        voice_say, take_photo, dispatch, telegram,
        # robot expression (the personality)
        reachy_look, reachy_antennas, reachy_body_turn, reachy_home, reachy_wake,
        reachy_express, reachy_list_emotions,
        reachy_get_state, reachy_look_at, reachy_camera,
        head_tracking, head_tracking_status,
        reachy_volume,   # "silent" → 0 before replying; TINY keeps listening at 0
    ]
    if use_spotify is not None:
        tools.append(use_spotify)
    tools.extend(tiny_mcp.get_tools(persona, fleet=fleet))
    return tools


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
    chat_id = os.getenv("TELEGRAM_DEFAULT_CHAT_ID", "")
    allowed = os.getenv("TELEGRAM_ALLOWED_USERS", "")
    primary_user = allowed.split(",")[0].strip() if allowed else "the user"
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
- See: take_photo(question) → the image lands in your own context; reachy_look_at(u, v).
- Follow faces: head_tracking(True/False), head_tracking_status().
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
    chat_id = os.getenv("TELEGRAM_DEFAULT_CHAT_ID", "")
    primary_user = (os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",") or [""])[0].strip()

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

3. **TELEGRAM A PHOTO + STATUS** to the primary user (chat={chat_disp}):
   telegram(action='send_photo', chat_id='{chat_id}',
            file_path='/tmp/tiny_view.jpg',
            caption='<one short sentence — what TINY sees + what it just did>')

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
        tg_disp=tg_block or "(no telegram history)", chat_id=chat_id, now_str=now_str,
    )
    return _resolve_body("thinker", _BASE + extra) + _agent_log_block(limit=30, exclude_persona="thinker")


# ── public factories ────────────────────────────────────────────────
def build_shell_agent() -> Agent:
    """REPL/shell agent: slim toolset + live-state header (agent.py runs this)."""
    return Agent(
        model=MODEL_ID,
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
    return Agent(model=MODEL_ID,
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
        if os.getenv("VOICE_MODEL"):
            kwargs["model_id"] = os.getenv("VOICE_MODEL")
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


def build_voice_agent(provider: str = "openai", voice: Optional[str] = None):
    """Build a BidiAgent + local PyAudio IO for TINY's voice persona.

    Returns (BidiAgent, audio_io). The caller drives the run loop.

    Reachy Mini's mic/speaker are on the same machine (Lite: laptop; Wireless:
    CM4), so we use the standard strands local audio IO (PyAudio) rather than a
    custom DDS transport like neon's G1BidiAudioIO. The head-wobble-on-speech
    is driven daemon-side via the SDK, so TINY still 'talks with its head'.
    """
    from strands.experimental.bidi import BidiAgent
    from strands.experimental.bidi.tools import stop_conversation

    model = _build_bidi_model(provider, voice)
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
