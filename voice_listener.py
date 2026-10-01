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

from tiny import build_voice_agent, voice_settings
from tools import config as _config

# VOICE_PROVIDER / VOICE_NAME are the bootstrap defaults of the cockpit config (`voice.*`, tools/config.py);
# every session reads the live values through voice_settings() at build time.
RESTART_DELAY = int(os.getenv("VOICE_RESTART_DELAY", "5"))
CONFIG_POLL_S = float(os.getenv("VOICE_CONFIG_POLL_S", "2"))     # how often the live session checks for a Settings change
SESSION_END_GRACE_S = 10.0                                      # graceful end budget before the run task is cancelled
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


class ConfigRestart(Exception):
    """The live session ended because the cockpit changed a voice-scoped setting; rebuild without backoff."""


async def request_session_end(agent) -> bool:
    """Ask a running 1.20 BidiAgent to end its conversation the way `stop_conversation` does: a
    BidiConnectionCloseEvent(reason="user_request") on the loop's event queue makes `receive()` return,
    `agent.run` then cancels the inputs and stops the model + IO in its own `finally`. Returns False
    when the private loop handle is missing (caller falls back to cancelling the run task)."""
    try:
        from strands.experimental.bidi.types.events import BidiConnectionCloseEvent
        loop = agent._loop
        cid = getattr(agent.model, "_connection_id", "unknown")
        await asyncio.wait_for(loop._event_queue.put(BidiConnectionCloseEvent(connection_id=cid, reason="user_request")),
                               timeout=SESSION_END_GRACE_S / 2)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[voice] graceful session end unavailable ({e.__class__.__name__}: {e}); cancelling", file=sys.stderr)
        return False


async def watch_config(agent, run_task: "asyncio.Task", *, generation_fn=None, poll_s: float = CONFIG_POLL_S,
                       scope: str = "voice") -> bool:
    """Poll the config generation while the session runs; on a change, end the session and return True.

    `generation_fn` defaults to tools.config.generation(scope). Returns False when run_task finished first."""
    gen_fn = generation_fn or (lambda: _config.generation(scope))
    start = await asyncio.to_thread(gen_fn)
    while not run_task.done():
        try:
            await asyncio.wait_for(asyncio.shield(run_task), timeout=poll_s)
            break                                   # the session ended on its own
        except asyncio.TimeoutError:
            pass
        now = await asyncio.to_thread(gen_fn)
        if now != start:
            vs = voice_settings()
            msg = (f"voice: config generation {start} -> {now}, restarting session "
                   f"(provider={vs['provider']}, model={vs['model'] or 'default'}, voice={vs['voice'] or 'default'})")
            print(f"[voice] {msg}", file=sys.stderr)
            try:
                from tools.agent_log import record as alog
                alog("voice", "system", msg)
            except Exception:  # noqa: BLE001
                pass
            if not await request_session_end(agent):
                run_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(run_task), timeout=SESSION_END_GRACE_S)
            except asyncio.TimeoutError:
                run_task.cancel()
                try:
                    await run_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            return True
    return False


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
    vs = voice_settings()                                       # cockpit config -> VOICE_* env -> defaults
    agent, audio_io = build_voice_agent(provider=vs["provider"], voice=vs["voice"] or None)
    # transcripts (what was heard / what TINY said) + tool calls → shared agent_log for the dashboard feed
    from tools.agent_log import BidiTranscriptSink
    from tools.head_tracking import SpeakingHandoff
    sink = BidiTranscriptSink("voice")
    # face tracking (daemon, 1.10+): weight 0 while TINY speaks, 1 afterwards — Pollen's set_speaking handoff
    handoff = SpeakingHandoff()
    model_id = getattr(agent.model, "model_id", "default")
    print(f"🎙 TINY voice up (provider={vs['provider']}, model={model_id}, "
          f"voice={vs['voice'] or 'default'}, config generation {_config.generation('voice')})", file=sys.stderr)
    print("   live mute: memory kv 'voice.muted' (true/false); /mute /unmute on Telegram; "
          "voice settings: cockpit Settings > Voice (the session restarts itself).", file=sys.stderr)
    # The session runs as a task so the config watcher can end it cleanly when the cockpit changes a voice
    # setting; agent.run's own finally still stops the model and the audio IO (no API change vs. awaiting it).
    run_task = asyncio.ensure_future(agent.run(inputs=[audio_io.input()], outputs=[audio_io.output(), sink, handoff]))
    if await watch_config(agent, run_task):
        raise ConfigRestart()
    await run_task                                              # re-raise whatever ended the session


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
        except ConfigRestart:
            delay = RESTART_DELAY
            print("[voice] rebuilding the session with the new settings", file=sys.stderr)
            continue                                   # no backoff: the owner asked for this restart
        except Exception as e:
            print(f"[voice err] {e}", file=sys.stderr)
            if stop["flag"]:
                break
            if time.monotonic() - started > 60:
                delay = RESTART_DELAY                      # a real session ran — the failure was transient
            if _is_fatal(e):
                provider = voice_settings()["provider"]
                print(f"[voice] fatal provider error (bad/revoked {provider.upper()} key, quota or model) — "
                      f"fix the key in .env (or the model/provider in the cockpit) and `systemctl --user restart tiny-voice`; "
                      f"retrying in {delay}s", file=sys.stderr)
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
