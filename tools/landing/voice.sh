#!/bin/sh
# voice.sh — the landing's one audio clip, honestly: the OFFLINE voice. On the CM4, tiny-tts.service runs Piper with
# en_US-lessac-medium (docs/start/systemd.md) and reachy_say() plays it through the speaker (tools/reachy_audio.py) — that is what
# the text personas and the dashboard sound like. (The live conversation voice is the realtime model's, not Piper's.)
# The line is reachy_say's own docstring example. Same public voice model (rhasspy/piper-voices, lessac medium, piper_version 1.0.0,
# sha256 5efe09e6…f019f), synthesized with piper-tts, then Opus 32k (+ AAC for Safari). Deterministic: re-running yields the same WAV.
# usage: sh tools/landing/voice.sh [venv-python]   (needs: pip install piper-tts; ffmpeg)
set -e
cd "$(dirname "$0")/../.."
PY=${1:-python3}
D=${PIPER_DATA_DIR:-/tmp/piper-voices}; mkdir -p "$D"
[ -f "$D/en_US-lessac-medium.onnx" ] || $PY -m piper.download_voices en_US-lessac-medium --data-dir "$D"
$PY - "$D" <<'PYEOF'
import sys, wave
from piper import PiperVoice
v = PiperVoice.load(f"{sys.argv[1]}/en_US-lessac-medium.onnx")
with wave.open("/tmp/hi-im-tiny.wav", "wb") as w: v.synthesize_wav("Hi, I'm TINY!", w)
PYEOF
ffmpeg -y -loglevel error -i /tmp/hi-im-tiny.wav -c:a libopus -b:a 32k -ac 1 docs/assets/landing/voice/hi-im-tiny.opus
ffmpeg -y -loglevel error -i /tmp/hi-im-tiny.wav -c:a aac -b:a 48k -ac 1 docs/assets/landing/voice/hi-im-tiny.m4a
ls -la docs/assets/landing/voice/
