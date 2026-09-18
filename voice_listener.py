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
RESTART_DELAY_MAX = int(os.getenv("VOICE_RESTART_DELAY_MAX", "300"))
# Daemon 1.10 owns mic+camera and PyAudio opens the ReSpeaker alongside it just fine (proven 2026-09-17: voice ran
# for hours while the dashboard held /api/media/acquire). Releasing is legacy from 1.8 — and it is destructive:
# POST /api/media/release tears down the daemon's unixfdsink camera socket, so every IPC camera client (dashboard,
# the daemon's own face tracker) dies with "Internal data stream error" and has to re-acquire. Opt back in with
# VOICE_RELEASE_MEDIA=1 (Lite / older daemons where ALSA is exclusive).
RELEASE_MEDIA = os.getenv("VOICE_RELEASE_MEDIA", "0").lower() in ("1", "true", "yes")
# Errors that no retry will fix — back off hard instead of hammering the provider (and the daemon) every 5 s.
_FATAL_MARKERS = ("invalid_api_key", "incorrect api key", "authentication", "unauthorized", "401", "insufficient_quota",
                  "billing", "permission", "model_not_found", "does not exist")


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


def _is_fatal(err: BaseException) -> bool:
    msg = str(err).lower()
    return any(m in msg for m in _FATAL_MARKERS)


async def run_once():
    if RELEASE_MEDIA:
        _release_daemon_media()
    # The audio board mutes the near end while the speaker plays unless PP_NLATTENONOFF=0 — no barge-in
    # otherwise. Runtime-only on the chip, so re-applied at every start (tools/xmos_audio.py has the numbers).
    try:
        from tools.xmos_audio import apply_params
        await asyncio.to_thread(apply_params)
    except Exception as e:  # noqa: BLE001
        print(f"[voice] XVF3800 tuning skipped: {e}", file=sys.stderr)
    agent, audio_io = build_voice_agent(provider=PROVIDER, voice=VOICE or None)
    # transcripts (what was heard / what TINY said) + tool calls → shared agent_log for the dashboard feed
    from tools.agent_log import BidiTranscriptSink
    from tools.head_tracking import SpeakingHandoff
    sink = BidiTranscriptSink("voice")
    # face tracking (daemon, 1.10+): weight 0 while TINY speaks, 1 afterwards — Pollen's set_speaking handoff
    handoff = SpeakingHandoff()
    model_id = getattr(agent.model, "model_id", "default")
    print(f"🎙 TINY voice up (provider={PROVIDER}, model={model_id}, "
          f"voice={VOICE or 'default'})", file=sys.stderr)
    print("   live mute: memory kv 'voice.muted' (true/false); /mute /unmute on Telegram.",
          file=sys.stderr)
    await agent.run(inputs=[audio_io.input()], outputs=[audio_io.output(), sink, handoff])


def main():
    stop = {"flag": False}
    def _sig(*_):
        stop["flag"] = True
    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    delay = RESTART_DELAY
    while not stop["flag"]:
        started = time.monotonic()
        try:
            asyncio.run(run_once())
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[voice err] {e}", file=sys.stderr)
            if stop["flag"]:
                break
            if time.monotonic() - started > 60:
                delay = RESTART_DELAY                      # a real session ran — the failure was transient
            if _is_fatal(e):
                print(f"[voice] fatal provider error (bad/revoked {PROVIDER.upper()} key, quota or model) — "
                      f"fix the key in .env and `systemctl --user restart tiny-voice`; retrying in {delay}s",
                      file=sys.stderr)
            else:
                print(f"[voice] restarting in {delay}s", file=sys.stderr)
            time.sleep(delay)
            delay = min(delay * 2, RESTART_DELAY_MAX)      # 5 → 10 → 20 … → 300 s
        else:
            delay = RESTART_DELAY
    try:                                   # Pollen moves.py ~661: never leave the daemon tracking headless
        from tools.head_tracking import stop_head_tracking
        stop_head_tracking()
    except Exception:  # noqa: BLE001
        pass
    print("👋 TINY voice listener stopped", file=sys.stderr)


if __name__ == "__main__":
    main()
