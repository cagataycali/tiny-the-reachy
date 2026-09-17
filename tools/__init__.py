"""TINY (Reachy Mini) @tool wrappers for the Strands agent.

Mirrors neon's tools/__init__.py organizing principle:
  - Robot control talks to the Reachy Mini daemon (localhost:8000 / reachy-mini.local:8000)
    via a cached singleton client (_reachy_common.get_mini()).
  - Cross-persona infra (memory / agent_log / voice_bridge / telegram / dispatch /
    prompts / manage_*) is copied verbatim from neon — identical SQLite-backed
    shared-brain so all four personas see what the others are doing.

    from tools import TINY_ALL_TOOLS
    agent = Agent(tools=[*TINY_ALL_TOOLS, shell, ...])
"""
# ── Robot control (Reachy Mini SDK) ──────────────────────────────────
from .reachy_motion import (
    reachy_look, reachy_antennas, reachy_body_turn, reachy_home, reachy_wake,
)
from .reachy_expression import reachy_express, reachy_list_emotions
from .reachy_state import reachy_get_state, reachy_motors
from .reachy_camera import reachy_camera, reachy_look_at, capture_camera
from .reachy_audio import reachy_play_sound, reachy_say, reachy_volume
from .head_tracking import head_tracking, head_tracking_status

# ── Cross-persona infra (shared brain — copied from neon) ─────────────
from .memory import memory
from .agent_log import (
    record as agent_log_record,
    recent as agent_log_recent,
    format_for_prompt as agent_log_format_for_prompt,
    stats as agent_log_stats,
    clear as agent_log_clear,
)
from .voice_bridge import (
    voice_say,
    push as voice_bridge_push,
    pop_pending as voice_bridge_pop_pending,
    flush_stale as voice_bridge_flush_stale,
    stats as voice_bridge_stats,
)
from .dispatch import dispatch
from .telegram import (
    telegram,
    record_message as telegram_record_message,
    format_history_for_prompt as telegram_format_history,
    download_file as telegram_download_file,
    listen as telegram_listen,
)
from .vision import take_photo
from .prompts import prompts
from .manage_messages import manage_messages
from .manage_tools import manage_tools


# ═══════════════════════════════════════════════════════════════════════
# Curated bundles
# ═══════════════════════════════════════════════════════════════════════

TINY_MOTION_TOOLS = [
    reachy_look, reachy_antennas, reachy_body_turn, reachy_home, reachy_wake,
]
TINY_EXPRESSION_TOOLS = [reachy_express, reachy_list_emotions]
TINY_STATE_TOOLS = [reachy_get_state, reachy_motors]
TINY_SENSING_TOOLS = [reachy_camera, reachy_look_at, capture_camera, head_tracking, head_tracking_status]
TINY_AUDIO_TOOLS = [reachy_play_sound, reachy_say, reachy_volume]

# Full robot toolset
TINY_ROBOT_TOOLS = (
    TINY_MOTION_TOOLS
    + TINY_EXPRESSION_TOOLS
    + TINY_STATE_TOOLS
    + TINY_SENSING_TOOLS
    + TINY_AUDIO_TOOLS
)

# Cross-persona stack (memory/voice/telegram/dispatch)
TINY_LOOKOUT_TOOLS = [
    memory, voice_say, dispatch, telegram, take_photo,
    prompts, manage_messages, manage_tools,
]

# Everything
TINY_ALL_TOOLS = TINY_ROBOT_TOOLS
TINY_TOOLS = TINY_ALL_TOOLS
