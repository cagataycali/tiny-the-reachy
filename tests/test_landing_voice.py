"""The landing's one sound is the offline Piper voice, small, labelled, and never autoplays."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "docs/overrides/home.html").read_text()
VOICE = ROOT / "docs/assets/landing/voice"


def test_voice_clip_is_small_and_referenced():
    opus, m4a = VOICE / "hi-im-tiny.opus", VOICE / "hi-im-tiny.m4a"
    assert opus.exists() and m4a.exists()
    assert opus.stat().st_size + m4a.stat().st_size < 60_000
    assert "assets/landing/voice/hi-im-tiny.opus" in HTML and "assets/landing/voice/hi-im-tiny.m4a" in HTML


def test_voice_never_autoplays_and_names_its_model():
    audio = re.search(r"<audio[^>]*>", HTML).group(0)
    assert "autoplay" not in audio and 'preload="none"' in audio
    block = HTML.split('id="l-voice"', 1)[1].split("</audio>", 1)[0]
    assert "en_US-lessac-medium" in block and "tiny-tts.service" in block and "realtime model" in block
    # the model name is the one the robot's unit runs (docs/start/systemd.md), not an invention
    assert "en_US-lessac-medium" in (ROOT / "docs/start/systemd.md").read_text()
