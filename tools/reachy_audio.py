"""TINY audio tools — play a sound file + speak text (TTS) with head-wobble sync.

The daemon plays audio through TINY's speaker. enable_wobbling() makes the head
bob in sync with playback — TINY's signature 'talking' motion.

TTS backend: ResembleAI Chatterbox Multilingual on HF Spaces (zero-shot voice
clone, 23 langs), same as the SDK's sound_tts example. Falls back gracefully
if gradio_client / network is unavailable.
"""
import os
import time
from strands import tool
from ._reachy_common import get_mini, ok, err

TTS_SPACE = os.getenv("TINY_TTS_SPACE", "ResembleAI/Chatterbox-Multilingual-TTS")
TTS_REF_AUDIO = os.getenv(
    "TINY_TTS_REF_AUDIO",
    "https://github.com/gradio-app/gradio/raw/main/test/test_files/audio_sample.wav",
)


@tool
def reachy_play_sound(sound_file: str, wobble: bool = True) -> dict:
    """Play a local/daemon sound file through TINY's speaker.

    Args:
        sound_file: path to a WAV/audio file the daemon can read, or a builtin
                    name like 'wake_up.wav' / 'go_sleep.wav'.
        wobble: enable head-wobble-on-audio during playback.
    """
    try:
        mini = get_mini()
        if wobble:
            mini.enable_wobbling()
        mini.media.play_sound(sound_file)
        return ok(f"played {sound_file}")
    except Exception as e:
        return err(f"reachy_play_sound failed: {e}")


@tool
def reachy_say(text: str, lang: str = "en", wobble: bool = True) -> dict:
    """Make TINY SPEAK text aloud via TTS, with synced head-wobble. USE to talk.

    This is TINY's voice for the shell/telegram/thinker personas (the always-on
    voice persona uses the realtime bidi model instead). Synthesizes speech,
    plays it on the speaker, wobbles the head.

    Args:
        text: what to say (<=300 chars per request works best).
        lang: ISO 639-1 code (en, fr, es, de, it, ja, zh, ...).
        wobble: bob the head while speaking.

    Examples:
        reachy_say("Hi, I'm TINY!")
        reachy_say("Bonjour tout le monde", lang="fr")
    """
    try:
        from gradio_client import Client, handle_file
    except ImportError:
        return err("gradio_client not installed — pip install gradio_client")
    try:
        client = Client(TTS_SPACE)
        audio_path = client.predict(
            text_input=text, language_id=lang,
            audio_prompt_path_input=handle_file(TTS_REF_AUDIO),
            api_name="/generate_tts_audio",
        )
        mini = get_mini()
        if wobble:
            mini.enable_wobbling()
        mini.media.play_sound(str(audio_path))
        # rough playback wait: ~0.06s/char, min 1.5s
        time.sleep(max(1.5, len(text) * 0.06))
        if wobble:
            mini.disable_wobbling()
        return ok(f"said: {text[:80]}")
    except Exception as e:
        return err(f"reachy_say failed: {e}")


@tool
def reachy_volume(level: int = -1) -> dict:
    """Get or set TINY's speaker volume (0-100). Omit level to just read it."""
    try:
        mini = get_mini()
        if level < 0:
            v = mini.media.get_volume() if hasattr(mini.media, "get_volume") else None
            return ok(f"volume = {v}", volume=v)
        if hasattr(mini.media, "set_volume"):
            mini.media.set_volume(int(level))
            return ok(f"volume set to {level}")
        return err("set_volume not supported by this media backend")
    except Exception as e:
        return err(f"reachy_volume failed: {e}")
