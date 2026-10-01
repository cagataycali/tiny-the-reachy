# MIGRATION — strands-agents bidi 1.20 → 1.57.1 (strands.bidi-ready)

Branch `feat/strands-bidi-1.57`. The robot (`/venvs/apps_venv`, Python 3.12) runs
strands-agents **1.20.0**; PyPI latest is **1.57.1** (2026-09-25). harness-sdk main
(#4707, unreleased) moved `strands.experimental.bidi` to `strands.bidi` and deletes the
experimental path in **v1.60.0**. This branch targets 1.57.1 today and `strands.bidi`
tomorrow through one module, `tools/bidi_compat.py`; nothing else in the repo names a
Strands bidi module or a `bidi_*` event string (`tests/test_bidi_compat.py` enforces it).

**1.20 is dropped, not shimmed.** `agent.send(TextBlock|ImageBlock)`, the model
constructors and the event names all changed shape; a two-version zoo would double every
code path. On 1.20 `tools/bidi_compat.py` raises one ImportError that names the pin.

## What changed (1.20 → 1.57.1)

| area | 1.20 (robot today) | 1.57.1 (this branch) | where |
|---|---|---|---|
| package | `strands.experimental.bidi` | `strands.bidi` first, experimental fallback | `tools/bidi_compat.py` |
| model classes | `BidiOpenAIRealtimeModel` / `BidiNovaSonicModel` / `BidiGeminiLiveModel` | `OpenAIRealtimeModel` / `BedrockNovaSonicModel` / `GoogleGeminiLiveModel`, lazy via `model_class(provider)` | `tiny.py::_build_bidi_model` |
| constructors | `provider_config={"audio": {"voice"}}`, `client_config={"api_key"|"region"}`, `model_id` optional | `model_id=` **required**, `voice=`, OpenAI `transcription_model_id=` + `api_key=` + `params=`, Bedrock `region=`, Gemini `client_args=` | `tiny.py` |
| default model ids | library defaults | `gpt-realtime-2` (robot's `VOICE_MODEL`), `amazon.nova-2-sonic-v1:0`, `gemini-3.8-live`; `VOICE_MODEL` overrides | `tiny.py::_DEFAULT_MODEL_IDS` |
| OpenAI VAD / transcription tuning | monkey patch of `_build_session_config` | **native** `params={"audio": {"input": {...}}}`, deep-merged by `_merge_config` | `tools/voice_session.py::session_params` |
| text / image input | `agent.send(BidiTextInputEvent)` / `BidiImageInputEvent` + a raw `_send_event` wire path and `_patch_openai_image_support` | `agent.send(ImageBlock(format, source={"bytes"}))` then `agent.send(TextBlock(q))`; `_send_image_content` is native and silent, the text send requests the one response | `tools/vision.py::_inject` |
| audio IO | `BidiAudioIO`, `_BidiAudioInput/_BidiAudioOutput(config)`, rates from `model.config["audio"]` | `AudioIO`, `_AudioInputStream/_AudioOutputStream(config, *, audio_processor)`, rates from `model.get_audio_config()`, input yields `AudioDelta(format, source)` | `resampling_audio.py` |
| output events | `bidi_audio_stream`, `bidi_transcript_stream(is_final)`, `bidi_response_complete`, `bidi_interruption`, `bidi_connection_close`, `bidi_error` | `bidi_audio_delta`, `bidi_transcript_delta` / `_stop`, `bidi_response_stop`, `bidi_barge_in`, `bidi_connection_stop`; errors are raised, not streamed | `EVENTS`, `LEGACY_EVENTS`, `event_type()` |
| hooks | `BidiMessageAddedEvent` | core `strands.hooks.MessageAddedEvent` (fired by `BidiAgent._append_messages`); bidi hooks `BidiResponseStopEvent`, `BidiBargeInEvent`, `BidiAgentStopEvent`, `Before/AfterConnectionRestartEvent` | `bidi_compat.hooks`, `tools/agent_log.py` |
| stop tool | `strands.experimental.bidi.tools.stop_conversation` | deprecated in 1.57.1, deleted on main (#4664). Ours: sets `request_state["stop_event_loop"]=True` (1.57 loop) **and** calls `agent.cancel()` when present (main) | `bidi_compat.stop_conversation` |
| session manager | `BidiAgent(session_manager=)` | still accepted in 1.57.1, removed on main (#4698); we never passed one | - |
| requirements | `strands-agents[bidi]` unpinned | `strands-agents[bidi]>=1.57.1,<1.60` | `requirements.txt` |

The 1.20 event names are still accepted by every sink for one release (`LEGACY_EVENTS`),
so a dashboard or peer that replays an old log keeps working. Drop the map at 1.60.

Tests: 89 passed on 1.57.1 / Python 3.12.9 (`python -m pytest tests -q`), PyAudio real
(portaudio), no robot. Offline smoke: `build_voice_agent("openai")` builds, the session
config carries VAD 0.6 / `tr` / `create_response` + `interrupt_response`, a synthetic
1.57.1 event stream through `BidiTranscriptSink` + `SpeakingHandoff` + `_ResamplingOutput`
records both transcripts, holds/releases tracking, and drops the post-barge-in straggler
(`~/.tiny/reachy-bidi-20261001/shots/events.log`). No live mic test: no OpenAI key on the
Mac. **The supervised voice test on the robot is the owner's step.**

## Robot upgrade recipe (owner, after the dashboard lane lands)

Disk on the CM4 is at 91 % (1.4 GB free), so purge first and install without a cache.

```bash
ssh pollen@reachy-mini.local        # or the robot's IP (dashboard/deploy/sync.sh uses REACHY_SSH)
systemctl --user stop tiny-voice
/venvs/apps_venv/bin/pip cache purge
/venvs/apps_venv/bin/pip install --no-cache-dir "strands-agents[bidi]>=1.57.1,<1.60"
/venvs/apps_venv/bin/python -c "import strands.experimental.bidi as b, importlib.metadata as m; print(m.version('strands-agents'), b.__file__)"
```

Then, from the Mac, the files (branch checked out at `~/tiny-the-reachy-bidi`):

```bash
rsync -av --exclude .venv --exclude .git --exclude .memory --exclude .env \
  ~/tiny-the-reachy-bidi/ pollen@reachy-mini.local:/home/pollen/tiny-the-reachy/
```

Back on the robot:

```bash
cd /home/pollen/tiny-the-reachy && /venvs/apps_venv/bin/python -m pytest tests -q   # expect 89 passed
systemctl --user restart tiny-voice
journalctl -b _SYSTEMD_USER_UNIT=tiny-voice.service -f      # wait for "TINY voice up (provider=openai, model=gpt-realtime-2"
```

Supervised check, in this order: say something (user transcript row in the dashboard
feed), let TINY answer (assistant row, head tracking weight 0 while speaking), talk over
it (barge-in: playback stops within a chunk, no straggler sentence), "look at me"
(`take_photo` → one spoken answer about the frame), "stop conversation" (session ends,
unit restarts in 5 s). Other units (`tiny-telegram`, `tiny-thinker`, `tiny-tts`,
`tiny-wake`, `tiny-beacon`, `tiny-tech`) do not import bidi and are untouched.

### Rollback

```bash
systemctl --user stop tiny-voice
/venvs/apps_venv/bin/pip install --no-cache-dir "strands-agents[bidi]==1.20.0"
# on the Mac: rsync main (3f38c19) the same way, or on the robot: git checkout main -- . if the tree is a clone
systemctl --user restart tiny-voice
```

The 1.20 files and the 1.57 files are disjoint only in `tools/bidi_compat.py`; everything
else is a modified file, so rollback is "old strands + old files", never a mix.

## Follow-ups for 1.58+ (strands.bidi)

- `IS_STABLE` turns True by itself when `strands.bidi` imports; drop the experimental
  fallback and `LEGACY_EVENTS` at 1.60.
- #4642 (main): `response.create` is deferred while user speech is pending — the
  `conversation_already_has_active_response` error in the robot's voice journal. 1.57.1
  does not have it; the native `_request_response` coalescing already removes the
  double-trigger `take_photo` used to cause. Re-test barge-in after the bump.
- main's `_build_session_config` runs before connect and refuses a session without
  `create_response=True` / `interrupt_response=True`; `voice_session.session_params()`
  already sets both (`session_config_is_valid` is that check, unit-tested).
- `agent.cancel()` is already honoured by our `stop_conversation`; when
  `request_state["stop_event_loop"]` stops being read (main), nothing changes for us.
- `SnapshotSessionManager` supports `BidiAgent` on main (#4603): voice memory across the
  5 s restarts (`take_snapshot` / `load_snapshot` exist in 1.57.1 already).
- Optional: `AudioIO(audio_processor=True)` (pywebrtc AEC, `strands-agents[bidi-aec]`) is
  pointless on the robot: the XMOS board does hardware AEC.

## git diff --stat main...feat/strands-bidi-1.57

```
 docs/guide/architecture.md     |   2 +-
 docs/reference/tools/vision.md |   2 +-
 requirements.txt               |   6 +-
 resampling_audio.py            |  80 +++++++++-------
 tests/test_barge_in.py         |  33 ++++++-
 tests/test_bidi_compat.py      | 147 +++++++++++++++++++++++++++++
 tests/test_head_tracking.py    |  14 +--
 tests/test_vision_inject.py    |  79 ++++++++--------
 tiny.py                        |  80 ++++++++--------
 tools/agent_log.py             |  40 ++++----
 tools/bidi_compat.py           | 205 +++++++++++++++++++++++++++++++++++++++++
 tools/head_tracking.py         |  16 ++--
 tools/vision.py                | 108 ++++------------------
 tools/voice_bridge.py          |   2 +-
 tools/voice_session.py         |  42 ++++-----
 15 files changed, 588 insertions(+), 268 deletions(-)
```
