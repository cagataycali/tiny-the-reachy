"""TINY camera tool — grab a frame from the head camera via the daemon.

The Reachy Mini daemon owns the camera. When REACHY_MEDIA_BACKEND is not
"no_media", the SDK client can pull frames. For multi-persona sharing (like
neon's dashboard-as-camera-owner pattern), one process holds a media backend
and others read the saved snapshot from a shared path.
"""
import os
import time
import tempfile
from pathlib import Path
from strands import tool
from ._reachy_common import get_mini, ok, err

SNAPSHOT = Path(os.getenv("TINY_CAMERA_SNAPSHOT",
                          str(Path(tempfile.gettempdir()) / "tiny_view.jpg")))


@tool
def reachy_camera(save_path: str = "", timeout: float = 10.0) -> dict:
    """Capture a frame from TINY's head camera and save it to disk.

    Requires the client to hold a media backend (REACHY_MEDIA_BACKEND=local
    or webrtc). If the daemon owns media in no_media mode, this reconnects a
    media-capable client for the grab.

    Args:
        save_path: where to write the JPEG (default: $TINY_CAMERA_SNAPSHOT).
        timeout: seconds to wait for a valid frame.

    Returns: status + path to the saved image.
    """
    try:
        import cv2
    except ImportError:
        return err("opencv not installed — pip install reachy_mini[opencv]")
    out = Path(save_path) if save_path else SNAPSHOT
    # 1) Preferred: the dashboard owns the camera (rpicam-vid on the Wireless CM4)
    #    and serves a fresh JPEG at /api/snapshot.jpg. One owner, everyone else
    #    reads the shared frame — no fight over /dev/video0.
    dash = os.getenv("TINY_DASHBOARD_URL", "http://127.0.0.1:8097")
    try:
        import urllib.request
        with urllib.request.urlopen(f"{dash}/api/snapshot.jpg", timeout=min(timeout, 5.0)) as r:
            data = r.read()
        if data[:2] == b"\xff\xd8" and len(data) > 5000:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            return ok(f"saved frame → {out} (via dashboard)", path=str(out), source="dashboard")
    except Exception:
        pass  # dashboard down → fall through to the SDK path
    try:
        # 2) Fallback: a media-capable SDK client grabs the frame itself.
        mini = get_mini(media_backend=os.getenv("REACHY_CAMERA_BACKEND", "local"))
        frame = mini.media.get_frame()
        t0 = time.time()
        while frame is None and time.time() - t0 < timeout:
            time.sleep(0.2)
            frame = mini.media.get_frame()
        if frame is None:
            return err(f"no frame within {timeout}s (camera busy or backend off)")
        out.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out), frame)
        return ok(f"saved frame → {out}", path=str(out))
    except Exception as e:
        return err(f"reachy_camera failed: {e}")


@tool
def reachy_look_at(u: int, v: int, duration: float = 1.0) -> dict:
    """Make TINY look at pixel (u,v) in its camera frame (visual servoing).

    Great for "look at me" / hand-tracking style behaviours. Requires a
    media-capable backend so the camera intrinsics are known.
    """
    try:
        mini = get_mini(media_backend=os.getenv("REACHY_CAMERA_BACKEND", "local"))
        mini.look_at_image(u=u, v=v, duration=duration)
        return ok(f"looking at pixel ({u},{v})")
    except Exception as e:
        return err(f"reachy_look_at failed: {e}")


@tool
def capture_camera(question: str = "") -> dict:
    """Grab a frame from TINY's head camera and return it as an IMAGE block (text personas only).

    For the telegram / thinker / shell personas (Bedrock Claude): the JPEG lands
    in the conversation so the model can SEE it. NOT for the realtime VOICE
    persona — OpenAI Realtime rejects image tool results and drops the session;
    voice must use take_photo() instead. Optional question is echoed for context.
    """
    r = reachy_camera()
    if r.get("status") != "success":
        return r
    try:
        path = next(c["json"]["path"] for c in r["content"] if isinstance(c, dict) and "json" in c)
        data = Path(path).read_bytes()
    except Exception as e:  # noqa: BLE001
        return err(f"capture_camera: frame saved but unreadable: {e}")
    text = f"camera frame ({len(data)//1024} KB)"
    if question:
        text += f" — question: {question}"
    return {"status": "success",
            "content": [{"text": text},
                        {"image": {"format": "jpeg", "source": {"bytes": data}}}]}
