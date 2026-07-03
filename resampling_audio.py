"""ResamplingAudioIO — bridge a fixed-rate audio device to a bidi model that
expects a different rate.

Reachy Mini's USB codec is locked to 16 kHz (in + out). OpenAI Realtime speaks
24 kHz PCM. This IO opens the PyAudio streams at the DEVICE rate (16 kHz) but
resamples on the fly with audioop.ratecv:

    mic  16k  --upsample-->  24k  -->  OpenAI   (input path)
    OpenAI 24k --downsample--> 16k -->  speaker (output path)

Nova Sonic (16 kHz) needs no resampling — set device_rate == model_rate and the
resampler becomes a no-op passthrough.

Drop-in replacement for strands' BidiAudioIO: exposes .input() / .output().
"""
import asyncio
import base64
import audioop
from typing import Any

import pyaudio

from strands.experimental.bidi.io.audio import (
    _BidiAudioInput, _BidiAudioOutput, _BidiAudioBuffer,
)
from strands.experimental.bidi.types.events import (
    BidiAudioInputEvent, BidiAudioStreamEvent, BidiInterruptionEvent, BidiOutputEvent,
)


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


class _ResamplingInput(_BidiAudioInput):
    """Mic input at device_rate, upsampled to the model's input_rate."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._device_rate = config.get("device_rate", 16000)
        self._ratecv_state = None

    async def start(self, agent) -> None:
        self._channels = agent.model.config["audio"]["channels"]
        self._format = agent.model.config["audio"]["format"]
        self._model_rate = agent.model.config["audio"]["input_rate"]

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

    async def __call__(self) -> BidiAudioInputEvent:
        data = await asyncio.to_thread(self._buffer.get)
        # Upsample device_rate -> model_rate before handing to the model.
        if self._device_rate != self._model_rate and data:
            data, self._ratecv_state = audioop.ratecv(
                data, 2, self._channels, self._device_rate, self._model_rate,
                self._ratecv_state,
            )
        return BidiAudioInputEvent(
            audio=base64.b64encode(data).decode("utf-8"),
            channels=self._channels,
            format=self._format,
            sample_rate=self._model_rate,
        )


class _ResamplingOutput(_BidiAudioOutput):
    """Speaker output at device_rate, downsampled from the model's output_rate."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._device_rate = config.get("device_rate", 16000)
        self._ratecv_state = None

    async def start(self, agent) -> None:
        self._channels = agent.model.config["audio"]["channels"]
        self._model_rate = agent.model.config["audio"]["output_rate"]

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

    async def __call__(self, event: BidiOutputEvent) -> None:
        if isinstance(event, BidiAudioStreamEvent):
            data = base64.b64decode(event["audio"])
            # Downsample model_rate -> device_rate before buffering for playback.
            if self._device_rate != self._model_rate and data:
                data, self._ratecv_state = audioop.ratecv(
                    data, 2, self._channels, self._model_rate, self._device_rate,
                    self._ratecv_state,
                )
            self._buffer.put(data)
        elif isinstance(event, BidiInterruptionEvent):
            self._buffer.clear()


class ResamplingAudioIO:
    """Drop-in BidiAudioIO that resamples between a fixed device rate and the
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
