"""Barge-in on the speaker side: an interruption flushes everything queued AND drops the
cancelled response's straggler deltas until the next response starts."""
import asyncio
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

pyaudio = pytest.importorskip("pyaudio")
pytest.importorskip("audioop", reason="audioop left the stdlib in 3.13 (robot runs 3.12; pip audioop-lts elsewhere)")
from resampling_audio import _ResamplingOutput  # noqa: E402


def _out():
    o = _ResamplingOutput({"device_rate": 16000})
    o._channels = 1
    o._model_rate = 16000          # no resampling → bytes in == bytes queued
    o._buffer.start()
    return o


def _audio(n=4, kind="bidi_audio_delta"):
    return {"type": kind, "audio": base64.b64encode(b"\x01\x02" * n).decode(), "format": "pcm",
            "sample_rate": 16000, "channels": 1}


def _barge():
    return {"type": "bidi_barge_in", "reason": "user_speech"}


def _queued(o):
    return sum(len(c) for c in list(o._buffer._buffer.queue)) + len(o._buffer._data)


def test_interruption_flushes_and_drops_stragglers():
    o = _out()
    asyncio.run(o({"type": "bidi_response_start", "response_id": "r1"}))
    asyncio.run(o(_audio())); asyncio.run(o(_audio()))
    assert _queued(o) == 16
    asyncio.run(o(_barge()))
    assert _queued(o) == 0
    asyncio.run(o(_audio()))                       # straggler of the cancelled response
    assert _queued(o) == 0 and o.stats["dropped_chunks"] == 1
    asyncio.run(o({"type": "bidi_response_start", "response_id": "r2"}))
    asyncio.run(o(_audio()))                       # the answer to the barge-in plays
    assert _queued(o) == 8
    assert o.stats["interruptions"] == 1


def test_partial_chunk_is_flushed_too():
    o = _out()
    asyncio.run(o({"type": "bidi_response_start", "response_id": "r1"}))
    asyncio.run(o(_audio(64)))                     # 128 bytes queued
    o._buffer.get(10)                               # speaker consumed 10 → 118 sit in _data
    assert len(o._buffer._data) == 118
    asyncio.run(o(_barge()))
    assert _queued(o) == 0


def test_interruption_with_no_active_response_does_not_mute_the_next_one():
    o = _out()
    asyncio.run(o(_barge()))
    asyncio.run(o({"type": "bidi_response_start", "response_id": "r1"}))
    asyncio.run(o(_audio()))
    assert _queued(o) == 8


def test_legacy_1_20_event_names_still_work_for_one_release():
    o = _out()
    asyncio.run(o({"type": "bidi_response_start", "response_id": "r1"}))
    asyncio.run(o(_audio(kind="bidi_audio_stream")))
    assert _queued(o) == 8
    asyncio.run(o({"type": "bidi_interruption", "reason": "user_speech"}))
    assert _queued(o) == 0 and o.stats["interruptions"] == 1


def test_output_is_a_strands_output_stream_without_the_transcript_printer():
    from tools.bidi_compat import audio_streams
    _, out_cls, _ = audio_streams()
    o = _out()
    assert isinstance(o, out_cls)
    assert o._audio_processor is None
    asyncio.run(o.stop())        # our stop never touches the rich transcript printer
