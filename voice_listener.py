#!/usr/bin/env python3
"""Always-on bidirectional voice agent for TINY (Reachy Mini).

Picks provider based on env (VOICE_PROVIDER, default: openai). Auto-restarts on
transient errors. Honours mute via memory kv `voice.muted`.

Audio path: local PyAudio (Reachy Mini mic + speaker are on the same machine).
Head-wobble-on-speech is driven daemon-side by the SDK, so TINY 'talks with
its head' automatically.
"""
import asyncio
import os
import signal
import sys
import time

from tiny import build_voice_agent

PROVIDER = os.getenv("VOICE_PROVIDER", "openai").lower()
VOICE = os.getenv("VOICE_NAME", "")
RESTART_DELAY = int(os.getenv("VOICE_RESTART_DELAY", "5"))


def _release_daemon_media():
    """Reachy daemon owns the mic/speaker by default; release so PyAudio can use it."""
    import urllib.request
    host = os.getenv("REACHY_HOST", "localhost")
    port = os.getenv("REACHY_PORT", "8000")
    try:
        urllib.request.urlopen(
            urllib.request.Request(f"http://{host}:{port}/api/media/release", method="POST"),
            timeout=5,
        ).read()
        print("[voice] daemon media released for PyAudio", file=sys.stderr)
    except Exception as e:
        print(f"[voice] media release failed (may already be released): {e}", file=sys.stderr)


async def run_once():
    _release_daemon_media()
    agent, audio_io = build_voice_agent(provider=PROVIDER, voice=VOICE or None)
    model_id = getattr(agent.model, "model_id", "default")
    print(f"🎙 TINY voice up (provider={PROVIDER}, model={model_id}, "
          f"voice={VOICE or 'default'})", file=sys.stderr)
    print("   live mute: memory kv 'voice.muted' (true/false); /mute /unmute on Telegram.",
          file=sys.stderr)
    await agent.run(inputs=[audio_io.input()], outputs=[audio_io.output()])


def main():
    stop = {"flag": False}
    def _sig(*_):
        stop["flag"] = True
    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    while not stop["flag"]:
        try:
            asyncio.run(run_once())
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[voice err] {e}", file=sys.stderr)
            if stop["flag"]:
                break
            time.sleep(RESTART_DELAY)
    print("👋 TINY voice listener stopped", file=sys.stderr)


if __name__ == "__main__":
    main()
