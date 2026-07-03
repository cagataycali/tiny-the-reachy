# environment variables

<span class="read-badge">⏱ 45s</span>

Everything TINY reads from `.env` (auto-loaded by both the Makefile and docker
compose). Copy `.env.example` → `.env` and fill in the secrets.

## model (REPL / telegram / thinker)

| var | default | note |
|---|---|---|
| `AWS_BEARER_TOKEN_BEDROCK` | — | Bedrock bearer token (preferred auth) |
| `AWS_DEFAULT_REGION` | `us-west-2` | Bedrock region |
| `TINY_MODEL_ID` | `global.anthropic.claude-opus-4-8` | model override |

## voice persona

| var | default | note |
|---|---|---|
| `OPENAI_API_KEY` | — | required for the default (OpenAI Realtime) voice |
| `VOICE_PROVIDER` | `openai` | `openai` · `nova_sonic` · `gemini` |
| `VOICE_NAME` | `alloy` | alloy/ash/ballad/coral/echo/sage/shimmer/verse |
| `VOICE_MODEL` | `gpt-realtime` | OpenAI only |
| `VOICE_RESTART_DELAY` | `5` | seconds before reconnecting |
| `GOOGLE_API_KEY` / `GEMINI_API_KEY` | — | for the Gemini Live voice provider |

## reachy daemon wiring

| var | default | note |
|---|---|---|
| `REACHY_HOST` | `reachy-mini.local` | daemon host (or IP, e.g. `192.168.1.5`) |
| `REACHY_PORT` | `8000` | daemon port |
| `REACHY_CONNECTION_MODE` | `auto` | `auto` · `localhost_only` · `network` |
| `REACHY_USE_SIM` | — | `1` → MuJoCo simulation, no hardware |
| `REACHY_MEDIA_BACKEND` | — | `no_media` · `local` · `webrtc` |
| `REACHY_CAMERA_BACKEND` | `local` | backend for transient frame grabs |
| `TINY_CAMERA_SNAPSHOT` | `/tmp/tiny_view.jpg` | default camera save path |

## TTS (`reachy_say`)

| var | default | note |
|---|---|---|
| `TINY_TTS_SPACE` | `ResembleAI/Chatterbox-Multilingual-TTS` | TTS backend |
| `TINY_TTS_REF_AUDIO` | — | URL/path to a reference voice for cloning |

## telegram persona

| var | default | note |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | bot token from @BotFather |
| `TELEGRAM_ALLOWED_USERS` | `cagataycali` | comma-separated usernames / numeric IDs |
| `TELEGRAM_DEFAULT_CHAT_ID` | — | thinker heartbeat destination |
| `TELEGRAM_HISTORY_LIMIT` | `20` | per-chat history depth |

## thinker loop

| var | default | note |
|---|---|---|
| `THINKER_INTERVAL` | `30` | seconds between heartbeats |
| `THINKER_DISABLED` | — | `1` → disable the thinker |

## devduck (used by `dispatch`)

| var | default | note |
|---|---|---|
| `DEVDUCK_AUTO_START_SERVERS` | `false` | keep sub-agents lean |
| `DEVDUCK_AMBIENT_MODE` | `false` | no background thinking in sub-agents |
| `BYPASS_TOOL_CONSENT` | `true` | non-interactive tool execution |
