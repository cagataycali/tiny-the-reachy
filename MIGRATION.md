# MIGRATION — strands-agents bidi 1.20 → harness-sdk main @ 957579a9 (1.57.2.dev54, `strands.bidi`)

Branch `feat/strands-bidi-1.57`. The robot (`/venvs/apps_venv`, Python 3.12) runs
strands-agents **1.20.0**. PyPI's latest is 1.57.1 (2026-09-25); it still ships bidi under
`strands.experimental.bidi` and lacks three things the robot needs. harness-sdk **main**
has them, so this branch runs strands **from source**, pinned to one sha:

| main-only fix | what it does for TINY |
|---|---|
| #4707 `strands.bidi` graduated | the stable package; the experimental path is a deprecation shim deleted in v1.60.0 |
| #4642 deferred `response.create` | the `conversation_already_has_active_response` errors in the robot's voice journal: a `take_photo` (or any text input) while the user is still speaking no longer races the VAD response |
| #4664 `BidiAgent.cancel()` | the stock `stop_conversation` tool and the `request_state["stop_event_loop"]` flag are gone; ours calls `agent.cancel()` |

One module, `tools/bidi_compat.py`, is the only place TINY names a Strands bidi module or a
`bidi_*` event string (`tests/test_bidi_compat.py` enforces it, and asserts `strands.bidi`
is the package in use and the installed build is a main build). **1.20 is dropped, not
shimmed**; on 1.20 the module raises one ImportError that names the recipe.

## Install from source (what we run)

`scripts/strands_wheel.sh` is the ONE pin (`STRANDS_SHA=957579a9`); `requirements.txt`
carries the same sha in a comment and the range `strands-agents[bidi]>=1.57.2.dev0,<1.60`
so a PyPI 1.58+ resolves later without a diff. The wheel is pure Python (0.85 MB) and is
never committed (`dist/` is gitignored).

```bash
# Mac, in the branch checkout (needs git + python3; hatchling/hatch-vcs come via pip build isolation)
scripts/strands_wheel.sh
#   wheel:   dist/wheels/strands_agents-1.57.2.dev54+g957579a9-py3-none-any.whl
#   version: 1.57.2.dev54+g957579a9 (harness-sdk @ 957579a9)
```

Facts behind the script (verified 2026-10-01 on the Mac):

- The version comes from hatch-vcs with `root=".."` and `tag_regex ^python/v`; the clone
  needs full history **and** tags (the script refuses a shallow or tagless clone).
- `pip install "strands-agents @ git+https://github.com/strands-agents/harness-sdk.git@957579a9#subdirectory=strands-py"`
  also works and yields the same `1.57.2.dev54+g957579a9` (pip's clone is full). It is
  NOT the robot recipe: the clone is 61 MB `.git` + 116 MB tree on a CM4 at 91 % disk.
- **Extras: `[bidi]` only.** `[bidi-openai]` pins `websockets>=16`, and `reachy_mini`
  (1.10 and 1.11) pins `websockets<16`; pip reports the conflict. The OpenAI realtime model
  uses only `websockets.connect(additional_headers=)` + `ClientConnection`, which
  websockets 15.0.1 has; `pip check` is clean and the model imports and builds its session.
  `[bidi-io]` (rich 15, prompt_toolkit — `strands.bidi.io.audio` imports the console
  module) is already satisfied on the robot by strands-agents-tools.
- Dry run against a mirror of the robot venv (strands 1.20 + tools, openai 1.109.1,
  google-genai 1.56, reachy_mini 1.10, aws_sdk_bedrock_runtime 0.2.0, websockets 15.0.1):
  `pip install "<wheel>[bidi]"` would install **9 wheels**: strands-agents itself plus the
  Bedrock/Smithy stack `aws_sdk_bedrock_runtime 0.11.0, awscrt 0.32.2, aws-sdk-signers 0.3.1,
  smithy-core 0.8.1, smithy-http 0.5.0, smithy-aws-core 0.11.0, smithy-aws-event-stream 0.3.0,
  smithy-json 0.3.0` (awscrt is the only sizeable one). openai, google-genai, reachy_mini,
  websockets, rich stay as they are. Run the same `--dry-run` on the robot before the real
  install and compare.

## What changed (1.20 → main @ 957579a9)

| area | 1.20 (robot today) | main @ 957579a9 (this branch) | where |
|---|---|---|---|
| package | `strands.experimental.bidi` | `strands.bidi` (experimental shim tolerated as a guarded fallback, never imported by anything else) | `tools/bidi_compat.py` |
| model classes | `BidiOpenAIRealtimeModel` / `BidiNovaSonicModel` / `BidiGeminiLiveModel` | `OpenAIRealtimeModel` / `BedrockNovaSonicModel` / `GoogleGeminiLiveModel`, lazy via `model_class(provider)` | `tiny.py::_build_bidi_model` |
| constructors | `provider_config={"audio": {"voice"}}`, `client_config={"api_key"|"region"}`, `model_id` optional | `model_id=` **required**, `voice=`; OpenAI `transcription_model_id=` **required kw** (None disables user transcription), `api_key=` **required at construction** (or `OPENAI_API_KEY`), `params=`; Bedrock `region=`; Gemini `client_args=` | `tiny.py` |
| default model ids | library defaults | `gpt-realtime-2` (robot's `VOICE_MODEL`), `amazon.nova-2-sonic-v1:0`, `gemini-3.8-live`; `VOICE_MODEL` overrides | `tiny.py::_DEFAULT_MODEL_IDS` |
| OpenAI VAD / transcription tuning | monkey patch of `_build_session_config` | **native** `params={"audio": {"input": {...}}}`, deep-merged by `_merge_config`; main refuses to connect without `create_response=True` + `interrupt_response=True` (we set both; `session_config_is_valid` is that check) | `tools/voice_session.py::session_params` |
| text / image input | `agent.send(BidiTextInputEvent)` / `BidiImageInputEvent` + a raw `_send_event` wire path and `_patch_openai_image_support` | **one** `agent.send([ImageBlock(format, source={"bytes"}), TextBlock(q)])` = one `BidiMessage`; the OpenAI model emits one `conversation.item.create` (`input_image`, `input_text`) and at most one `response.create`, deferred while `input_audio_pending` (#4642) and coalesced while a response or tool call is in flight | `tools/vision.py::_inject` |
| audio IO | `BidiAudioIO`, `_BidiAudioInput/_BidiAudioOutput(config)`, rates from `model.config["audio"]` | `AudioIO`; `_AudioInputStream(config, *, audio_processor)`, `_AudioOutputStream(config, *, console, audio_processor)` (main added the `ConsoleIO` transcript printer; we pass a never-started null console), rates from `model.get_audio_config()`, input yields `AudioDelta(format, source)` | `resampling_audio.py` |
| output events | `bidi_audio_stream`, `bidi_transcript_stream(is_final)`, `bidi_response_complete`, `bidi_interruption`, `bidi_connection_close`, `bidi_error` | `bidi_audio_delta`, `bidi_transcript_delta` / `_stop`, `bidi_response_stop`, `bidi_barge_in`, `bidi_connection_stop`; errors are raised, not streamed | `EVENTS`, `LEGACY_EVENTS`, `event_type()` |
| hooks | `BidiMessageAddedEvent` | core `strands.hooks.MessageAddedEvent` (fired by `BidiAgent._append_messages`); bidi hooks `BidiResponseStopEvent`, `BidiBargeInEvent`, `BidiAgentStopEvent`, `Before/AfterConnectionRestartEvent` | `bidi_compat.hooks`, `tools/agent_log.py` |
| stop tool | `strands.experimental.bidi.tools.stop_conversation` | deleted (#4664). Ours: `tool_context.agent.cancel()` (thread-safe, honoured after the current tool group); no `request_state` flag, it does not exist on main | `bidi_compat.stop_conversation` |
| session manager | `BidiAgent(session_manager=)` | removed (#4698); we never passed one. `SnapshotSessionManager` supports `BidiAgent` (#4603), not adopted here | - |
| requirements | `strands-agents[bidi]` unpinned | `strands-agents[bidi]>=1.57.2.dev0,<1.60` built from source @ 957579a9 | `requirements.txt`, `scripts/strands_wheel.sh` |

The 1.20 event names are still accepted by every sink for one release (`LEGACY_EVENTS`),
so a dashboard or peer that replays an old log keeps working. Drop the map at 1.60.

Tests: **93 passed** on `strands_agents-1.57.2.dev54+g957579a9` / Python 3.12.9
(`python -m pytest tests -q`), PyAudio real (portaudio), no robot. `python -W
error::DeprecationWarning -c "import tiny"` passes (no experimental path at import). Docs
budget 6,397 / 6,400. Offline smoke (`~/.tiny/reachy-bidi-20261001/shots/events.log`):
`build_voice_agent("openai", voice="shimmer")` builds on the real model, the session config
carries VAD 0.6 / `tr` / `create_response` + `interrupt_response`, `stop_conversation`
flips `agent.cancel_signal`, a `take_photo` through the real `OpenAIRealtimeModel` with the
websocket recorded is `conversation.item.create` + one `response.create`, the same call
while the user speaks sends only the item and the `response.create` follows once speech
ends, and a synthetic event stream through `BidiTranscriptSink` + `SpeakingHandoff` +
`_ResamplingOutput` records both transcripts, holds/releases tracking and drops the
post-barge-in straggler. No live mic test: no OpenAI key on the Mac. **The supervised
voice test on the robot is the owner's step.**

## Robot upgrade recipe (owner, after the dashboard lane lands)

Disk on the CM4 is at 91 % (1.4 GB free): purge the pip cache first, install without one.
pytest is not installed on the robot and is not needed there.

```bash
# 1. Mac: build + copy the wheel (branch checked out at ~/tiny-the-reachy-bidi)
cd ~/tiny-the-reachy-bidi && scripts/strands_wheel.sh
scp dist/wheels/strands_agents-1.57.2.dev54+g957579a9-py3-none-any.whl pollen@reachy-mini.local:/tmp/

# 2. Robot: stop the voice unit, swap strands (the other units do not import bidi)
systemctl --user stop tiny-voice
/venvs/apps_venv/bin/pip cache purge
/venvs/apps_venv/bin/pip install --dry-run --no-cache-dir "/tmp/strands_agents-1.57.2.dev54+g957579a9-py3-none-any.whl[bidi]"   # expect the 9 wheels listed above, nothing else
/venvs/apps_venv/bin/pip install --no-cache-dir "/tmp/strands_agents-1.57.2.dev54+g957579a9-py3-none-any.whl[bidi]"
/venvs/apps_venv/bin/python -c "import strands.bidi as b, importlib.metadata as m; print(m.version('strands-agents'), b.__file__)"
#   -> 1.57.2.dev54+g957579a9 /venvs/apps_venv/lib/python3.12/site-packages/strands/bidi/__init__.py

# 3. Mac: the branch files
rsync -av --exclude .venv --exclude .git --exclude .memory --exclude .env --exclude dist \
  ~/tiny-the-reachy-bidi/ pollen@reachy-mini.local:/home/pollen/tiny-the-reachy/

# 4. Robot: start and watch
systemctl --user restart tiny-voice
journalctl -b _SYSTEMD_USER_UNIT=tiny-voice.service -f
#   wait for "TINY voice up (provider=openai, model=gpt-realtime-2"
#   and the ABSENCE of "conversation_already_has_active_response" across a few turns
```

Supervised check, in this order: say something (user transcript row in the dashboard
feed), let TINY answer (assistant row, head tracking weight 0 while speaking), talk over
it (barge-in: playback stops within a chunk, no straggler sentence), "look at me" while
TINY is quiet and once while you are still talking (`take_photo` → one spoken answer about
the frame, no error line in the journal), "stop conversation" (session ends, unit restarts
in 5 s). Other units (`tiny-telegram`, `tiny-thinker`, `tiny-tts`, `tiny-wake`,
`tiny-beacon`, `tiny-tech`) do not import bidi and are untouched.

### Rollback

```bash
systemctl --user stop tiny-voice
/venvs/apps_venv/bin/pip install --no-cache-dir "strands-agents[bidi]==1.20.0"
# Mac: rsync main (3f38c19) the same way, or on the robot: git checkout main -- . if the tree is a clone
systemctl --user restart tiny-voice
```

The 1.20 files and the branch files differ in every migrated module (not only
`tools/bidi_compat.py`), so rollback is "old strands + old files", never a mix. The
Bedrock/Smithy wheels the upgrade pulled are harmless under 1.20 and can stay.

## Follow-ups (not in this branch)

Done by targeting main: #4642 (deferred `response.create`), #4664 (`agent.cancel()`),
`strands.bidi` imports, the pre-connect `create_response`/`interrupt_response` check.

- **Re-pin on the next PyPI release.** When 1.58+ ships `strands.bidi`, set
  `requirements.txt` to that version, delete `scripts/strands_wheel.sh` and the sha comment,
  and drop the experimental fallback + `LEGACY_EVENTS` at 1.60.
- **`audioop` is deprecated in Python 3.12 and removed in 3.13.** `resampling_audio.py`
  uses `audioop.ratecv` for 16 k ↔ 24 k. Fine on the robot's 3.12 (one DeprecationWarning
  at import); before any Python bump swap in `audioop-lts` or a numpy resampler.
- Optional, listed only: `SnapshotSessionManager` for voice memory across the 5 s
  restarts (#4603, supports `BidiAgent`); `AudioIO(audio_processor=True)` (pywebrtc AEC,
  `[bidi-aec]`) is pointless on the robot because the XMOS board does hardware AEC;
  `ConsoleIO` is never started by TINY (headless under systemd).

## git diff --stat main...feat/strands-bidi-1.57

```
 .gitignore                     |   3 +
 MIGRATION.md                   | 159 ++++++++++++++++++++++++++++++++
 docs/guide/architecture.md     |   2 +-
 docs/reference/tools/vision.md |   2 +-
 requirements.txt               |  12 ++-
 resampling_audio.py            | 103 ++++++++++++++-------
 scripts/strands_wheel.sh       |  47 ++++++++++
 tests/test_barge_in.py         |  33 ++++++-
 tests/test_bidi_compat.py      | 183 ++++++++++++++++++++++++++++++++++++
 tests/test_head_tracking.py    |  14 +--
 tests/test_vision_inject.py    | 147 +++++++++++++++++++++--------
 tiny.py                        |  80 ++++++++--------
 tools/agent_log.py             |  40 ++++----
 tools/bidi_compat.py           | 205 +++++++++++++++++++++++++++++++++++++++++
 tools/head_tracking.py         |  16 ++--
 tools/vision.py                | 109 ++++------------------
 tools/voice_bridge.py          |   2 +-
 tools/voice_session.py         |  42 ++++-----
 18 files changed, 931 insertions(+), 268 deletions(-)
```
