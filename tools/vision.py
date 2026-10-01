"""Vision tool — capture a TINY camera frame and send it to the bidi voice agent
(``agent.send([ImageBlock, TextBlock])``, strands.bidi), so the realtime model SEES the image
natively. Adapted from neon/tools/vision.py.

On Reachy Mini the frame comes from the daemon camera (reachy_camera tool) or,
as a dev fallback on macOS, from ffmpeg avfoundation.
"""
import os
import platform
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from strands import tool

from .bidi_compat import ImageBlock, TextBlock, realtime_model_class

CACHE_DIR = Path(tempfile.gettempdir()) / "tiny_vision"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _realtime_model_class():
    """OpenAIRealtimeModel via the compat layer (None when websockets is missing)."""
    return realtime_model_class()


def _capture_frame_macos(device: int = 0) -> Path:
    output = CACHE_DIR / f"frame_{int(time.time())}.jpg"
    cmd = [
        "ffmpeg", "-y", "-f", "avfoundation", "-framerate", "30",
        "-video_size", "1280x720", "-i", str(device),
        "-frames:v", "1", "-q:v", "3", str(output),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if r.returncode != 0 or not output.exists():
        raise RuntimeError(f"ffmpeg failed: {r.stderr[-500:]}")
    return output


def _capture_frame(device: int = 0) -> Path:
    # Prefer the real robot camera via the reachy_camera tool.
    try:
        from .reachy_camera import reachy_camera
        out = CACHE_DIR / f"frame_{int(time.time())}.jpg"
        r = reachy_camera(save_path=str(out))
        if r.get("status") == "success" and out.exists():
            return out
    except Exception:
        pass
    # Dev fallback: macOS FaceTime camera.
    if platform.system() == "Darwin" and shutil.which("ffmpeg"):
        return _capture_frame_macos(device=device)
    raise RuntimeError("no camera frame available (daemon camera + ffmpeg both failed)")


async def _inject(agent, img_bytes: bytes, question: str, fmt: str = "jpeg") -> None:
    """Put the frame and the question in front of the model as ONE user message.

    strands.bidi (harness-sdk main): ``agent.send([ImageBlock, TextBlock])`` builds one
    ``BidiMessage`` with both blocks in order; the OpenAI model turns it into a single
    ``conversation.item.create`` (``input_image`` then ``input_text``) followed by at most one
    ``response.create``, which ``_flush_response_request`` DEFERS while the user is still
    speaking (``input_audio_pending``, #4642) or another response / tool call is in flight.
    That is the fix for the ``conversation_already_has_active_response`` errors the robot
    logged on 1.20, where this tool pushed a raw ``response.create`` over the wire.
    """
    await agent.send([ImageBlock(format=fmt, source={"bytes": img_bytes}), TextBlock(question)])


DEFAULT_QUESTION = os.getenv(
    "TINY_PHOTO_QUESTION",
    "This is what your head camera sees right now. Say briefly what you see; "
    "if there is a person, describe them and what they are doing.",
)


@tool(context=True)
async def take_photo(tool_context, question: str = "", device: int = 0) -> dict:
    """LOOK. Capture a frame from TINY's head camera and put it in front of the
    voice model right now — the model sees the image and answers in audio.

    Call this FIRST whenever someone says "look at me", "what do you see",
    "who's there", "what is this", "can you see …" — never answer about what
    you see without calling it, and never say "I'll take a look" instead of
    calling it.

    Args:
        question: what to answer about the image (default: describe what you see).
        device: dev fallback camera index (macOS). Ignored on the robot.
    """
    agent = getattr(tool_context, "agent", None) if tool_context else None
    if agent is None or not hasattr(agent, "send"):
        return {"status": "error",
                "message": "take_photo only works inside a running BidiAgent"}
    try:
        image_path = _capture_frame(device=device)
    except Exception as e:
        return {"status": "error", "stage": "capture", "message": str(e)}

    q = question.strip() or DEFAULT_QUESTION
    try:
        await _inject(agent, image_path.read_bytes(), q)
    except Exception as e:
        return {"status": "error", "stage": "inject", "message": str(e),
                "image_path": str(image_path)}
    return {"status": "success", "image_path": str(image_path),
            "question": q, "device": device,
            "note": "Image injected into the realtime stream; answer in audio about what you see."}
