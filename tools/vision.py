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


def _realtime_model_class():
    """Find BidiOpenAIRealtimeModel across Strands versions (1.20: openai_realtime, 1.5x: openai)."""
    for mod in ("strands.experimental.bidi.models.openai_realtime",
                "strands.experimental.bidi.models.openai"):
        try:
            import importlib
            return getattr(importlib.import_module(mod), "BidiOpenAIRealtimeModel")
        except (ImportError, AttributeError):
            continue
    return None


def _patch_openai_image_support() -> None:
    """Add BidiImageInputEvent dispatch to BidiOpenAIRealtimeModel (idempotent).

    Strands < 1.5x has no image path on the Realtime model. We add one that
    mirrors what newer Strands does natively: a user ``input_image`` item
    followed by ``response.create`` — WITHOUT the response.create the image
    sits in the conversation and the model stays silent until the next
    utterance, which is what "TINY doesn't see me in voice" looked like.
    On a Strands that already ships ``_send_image_content`` this is a no-op.
    """
    cls = _realtime_model_class()
    if cls is None or getattr(cls, "_image_patched", False):
        return
    if hasattr(cls, "_send_image_content"):
        cls._image_patched = True   # native support (Strands >= 1.5x) — leave it alone
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
        await self._send_event({"type": "response.create"})

    _orig_send = cls.send

    async def _patched_send(self, content):
        if isinstance(content, BidiImageInputEvent):
            if not self._connection_id:
                raise RuntimeError("model not started | call start before sending")
            await self._send_image_content(content)
            return
        await _orig_send(self, content)

    cls._send_image_content = _send_image_content
    cls.send = _patched_send
    cls._image_patched = True


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


async def _inject(agent, img_b64: str, question: str) -> None:
    """Put ONE user message (question + image) in front of the realtime model and ask
    for ONE response.

    On OpenAI Realtime we talk to the wire directly: a single
    ``conversation.item.create`` carrying ``input_text`` + ``input_image`` and a single
    ``response.create``. Going through ``agent.send`` twice (text, then image) yields
    two responses on Strands >= 1.5x (both sends trigger one) and, on 1.20, a reply
    about the text before the image has arrived. Other providers fall back to
    ``agent.send`` (image, then question).
    """
    model = getattr(agent, "model", None)
    send_event = getattr(model, "_send_event", None)
    if send_event is not None and getattr(model, "_connection_id", None):
        item = {
            "type": "message",
            "role": "user",
            "content": [
                {"type": "input_text", "text": question},
                {"type": "input_image", "image_url": f"data:image/jpeg;base64,{img_b64}"},
            ],
        }
        await send_event({"type": "conversation.item.create", "item": item})
        await send_event({"type": "response.create"})
        return
    await agent.send(BidiImageInputEvent(image=img_b64, mime_type="image/jpeg"))
    await agent.send(BidiTextInputEvent(text=question, role="user"))


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
    img_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    try:
        await _inject(agent, img_b64, q)
    except Exception as e:
        return {"status": "error", "stage": "inject", "message": str(e),
                "image_path": str(image_path)}
    return {"status": "success", "image_path": str(image_path),
            "question": q, "device": device,
            "note": "Image injected into the realtime stream; answer in audio about what you see."}
