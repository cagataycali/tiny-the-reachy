"""Vision tool — capture a TINY camera frame and inject it into the bidi voice
agent's multimodal context (BidiImageInputEvent), so the realtime model SEES
the image natively. Adapted from neon/tools/vision.py.

On Reachy Mini the frame comes from the daemon camera (reachy_camera tool) or,
as a dev fallback on macOS, from ffmpeg avfoundation.
"""
import base64
import os
import platform
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from strands import tool
from strands.experimental.bidi.types.events import (
    BidiImageInputEvent,
    BidiTextInputEvent,
)

CACHE_DIR = Path(tempfile.gettempdir()) / "tiny_vision"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _patch_openai_image_support() -> None:
    """Add BidiImageInputEvent dispatch to BidiOpenAIRealtimeModel (idempotent)."""
    try:
        from strands.experimental.bidi.models.openai_realtime import (
            BidiOpenAIRealtimeModel,
        )
    except ImportError:
        return
    if getattr(BidiOpenAIRealtimeModel, "_image_patched", False):
        return

    async def _send_image_content(self, image_input: BidiImageInputEvent) -> None:
        b64 = image_input.image
        mime = image_input.mime_type or "image/jpeg"
        data_url = f"data:{mime};base64,{b64}"
        item = {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_image", "image_url": data_url}],
        }
        await self._send_event({"type": "conversation.item.create", "item": item})

    _orig_send = BidiOpenAIRealtimeModel.send

    async def _patched_send(self, content):
        if isinstance(content, BidiImageInputEvent):
            if not self._connection_id:
                raise RuntimeError("model not started | call start before sending")
            await self._send_image_content(content)
            return
        await _orig_send(self, content)

    BidiOpenAIRealtimeModel._send_image_content = _send_image_content
    BidiOpenAIRealtimeModel.send = _patched_send
    BidiOpenAIRealtimeModel._image_patched = True


_patch_openai_image_support()


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


@tool(context=True)
async def take_photo(tool_context, question: str = "", device: int = 0) -> dict:
    """Capture a frame from TINY's camera and inject it into the voice agent's
    multimodal context. The realtime model sees the image and replies in audio.

    Use when the user says "look at me", "what do you see?", "who's there?".

    Args:
        question: optional follow-up text sent after the image.
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

    img_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    try:
        await agent.send(BidiImageInputEvent(image=img_b64, mime_type="image/jpeg"))
        if question.strip():
            await agent.send(BidiTextInputEvent(text=question.strip(), role="user"))
    except Exception as e:
        return {"status": "error", "stage": "inject", "message": str(e),
                "image_path": str(image_path)}
    return {"status": "success", "image_path": str(image_path),
            "question": question or "(model will decide)", "device": device,
            "note": "Image injected into bidi stream. Model responds in audio."}
