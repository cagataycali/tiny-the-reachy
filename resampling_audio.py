"""ResamplingAudioIO — bridge a fixed-rate audio device to a bidi model that
expects a different rate.

Reachy Mini's USB codec is locked to 16 kHz (in + out). OpenAI Realtime speaks
24 kHz PCM. This IO opens the PyAudio streams at the DEVICE rate (16 kHz) but
resamples on the fly with audioop.ratecv:

    mic  16k  --upsample-->  24k  -->  OpenAI   (input path)
    OpenAI 24k --downsample--> 16k -->  speaker (output path)

Nova Sonic (16 kHz) needs no resampling — set device_rate == model_rate and the
resampler becomes a no-op passthrough.

Drop-in replacement for strands' AudioIO (strands.bidi, harness-sdk main): exposes
.input() / .output(). Built on the private _AudioInputStream / _AudioOutputStream (via
tools.bidi_compat) because AudioIO validates that the device rate equals the model rate
and has no resampler of its own. Model rates come from ``agent.model.get_audio_config()``.
Main's output stream also owns a rich/prompt_toolkit ConsoleIO transcript printer; TINY
runs headless under systemd, so a no-op console stands in and is never started.
"""
import asyncio
import audioop
import base64
from typing import Any

import pyaudio

from tools.bidi_compat import EVENTS, AudioDelta, audio_streams, event_type

_AudioInputStream, _AudioOutputStream, _AudioBuffer = audio_streams()


class _NullConsoleOutput:
    """What ``ConsoleIO.output()`` returns, minus the terminal: never started, never written."""

    async def start(self, agent) -> None:  # pragma: no cover - the subclass never calls it
        return None

    async def stop(self) -> None:  # pragma: no cover
        return None

    async def __call__(self, event) -> None:  # pragma: no cover
        return None


class _NullConsole:
    """Stand-in for strands' ConsoleIO: main's _AudioOutputStream requires one at construction
    (``console=``) to print transcripts to a TTY. The transcript goes to tools.agent_log instead."""

    def output(self) -> _NullConsoleOutput:
        return _NullConsoleOutput()


def _find_device(kind: str) -> int | None:
    """Locate the reachy audio sink/src by name. kind in {'out','in'}."""
    p = pyaudio.PyAudio()
    try:
        want = "sink" if kind == "out" else "src"
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            name = info.get("name", "")
            if "reachymini" in name and want in name:
                return i
            if want == "out" and info.get("maxOutputChannels", 0) > 0 and "reachy" in name.lower():
                return i
            if want == "in" and info.get("maxInputChannels", 0) > 0 and "reachy" in name.lower():
                return i
        return None
    finally:
        p.terminate()


class _ResamplingInput(_AudioInputStream):
    """Mic input at device_rate, upsampled to the model's input rate."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config, audio_processor=None)
        self._device_rate = config.get("device_rate", 16000)
        self._ratecv_state = None

    async def start(self, agent) -> None:
        cfg = agent.model.get_audio_config()["input"]
        self._channels = cfg["channels"]
        self._format = cfg["format"]
        self._model_rate = cfg["sample_rate"]

        self._buffer.start()
        self._audio = pyaudio.PyAudio()
        # Open at the DEVICE rate (what the codec actually supports).
        self._stream = self._audio.open(
            channels=self._channels,
            format=pyaudio.paInt16,
            frames_per_buffer=self._frames_per_buffer,
            input=True,
            input_device_index=self._device_index,
            rate=self._device_rate,
            stream_callback=self._callback,
        )

    async def __call__(self) -> AudioDelta:
        data = await asyncio.to_thread(self._buffer.get)
        # Upsample device_rate -> model_rate before handing to the model.
        if self._device_rate != self._model_rate and data:
            data, self._ratecv_state = audioop.ratecv(
                data, 2, self._channels, self._device_rate, self._model_rate,
                self._ratecv_state,
            )
        return AudioDelta(format=self._format, source={"bytes": data})


class _ResamplingOutput(_AudioOutputStream):
    """Speaker output at device_rate, downsampled from the model's output rate.

    Barge-in hardening (measured 2026-09-18 on the robot — the XMOS board's hardware
    AEC cancels our own playback completely, so a user really talking over TINY is
    what reaches the model, and the client must honour the interruption fully):

    * on ``bidi_barge_in`` the playback queue AND the partially consumed chunk
      are dropped, the resampler filter state is reset, and every further audio
      delta is DROPPED until the next ``bidi_response_start`` — OpenAI keeps
      streaming the cancelled response for one network round-trip after
      ``speech_started`` and, because it generates faster than realtime, those
      stragglers were a second or two of the old sentence blurted after the user
      had already started talking.

    Accepts the 1.20 names (``bidi_interruption`` / ``bidi_audio_stream``) for one
    release via ``tools.bidi_compat.event_type``.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config, console=_NullConsole(), audio_processor=None)
        self._device_rate = config.get("device_rate", 16000)
        self._ratecv_state = None
        self._drop_until_next_response = False
        self.stats = {"interruptions": 0, "dropped_chunks": 0, "dropped_bytes": 0}

    async def start(self, agent) -> None:
        cfg = agent.model.get_audio_config()["output"]
        self._channels = cfg["channels"]
        self._model_rate = cfg["sample_rate"]

        self._buffer.start()
        self._audio = pyaudio.PyAudio()
        # Open at the DEVICE rate.
        self._stream = self._audio.open(
            channels=self._channels,
            format=pyaudio.paInt16,
            frames_per_buffer=self._frames_per_buffer,
            output=True,
            output_device_index=self._device_index,
            rate=self._device_rate,
            stream_callback=self._callback,
        )

    async def stop(self) -> None:
        # The stock stream also stops the ConsoleIO transcript printer we never started.
        if hasattr(self, "_stream"):
            self._stream.close()
        if hasattr(self, "_audio"):
            self._audio.terminate()
        if hasattr(self, "_buffer"):
            self._buffer.stop()

    def _flush(self) -> None:
        """Drop everything queued for the speaker, including the half-consumed chunk."""
        self._buffer.clear()
        data = getattr(self._buffer, "_data", None)
        if data is not None:
            data.clear()
        self._ratecv_state = None

    def _callback(self, _in_data, frame_count, *_):
        """PyAudio pull: no audio processor, so plain buffer read (parent would feed AEC)."""
        byte_count = frame_count * self._channels * pyaudio.get_sample_size(pyaudio.paInt16)
        return (self._buffer.get(byte_count), pyaudio.paContinue)

    async def __call__(self, event) -> None:
        etype = event_type(event)
        if etype == EVENTS.RESPONSE_START:
            self._drop_until_next_response = False
            return
        if etype == EVENTS.BARGE_IN:
            self.stats["interruptions"] += 1
            self._drop_until_next_response = True
            self._flush()
            return
        if etype == EVENTS.AUDIO_DELTA:
            data = base64.b64decode(event["audio"])
            if self._drop_until_next_response:
                self.stats["dropped_chunks"] += 1
                self.stats["dropped_bytes"] += len(data)
                return
            # Downsample model_rate -> device_rate before buffering for playback.
            if self._device_rate != self._model_rate and data:
                data, self._ratecv_state = audioop.ratecv(
                    data, 2, self._channels, self._model_rate, self._device_rate,
                    self._ratecv_state,
                )
            self._buffer.put(data)


class ResamplingAudioIO:
    """Drop-in AudioIO that resamples between a fixed device rate and the
    model's rate. Auto-detects the Reachy Mini USB codec devices if indices
    are not supplied.
    """

    def __init__(self, device_rate: int = 16000, **config: Any) -> None:
        config.setdefault("input_device_index", _find_device("in"))
        config.setdefault("output_device_index", _find_device("out"))
        config["device_rate"] = device_rate
        self._config = config

    def input(self) -> _ResamplingInput:
        return _ResamplingInput(self._config)

    def output(self) -> _ResamplingOutput:
        return _ResamplingOutput(self._config)
