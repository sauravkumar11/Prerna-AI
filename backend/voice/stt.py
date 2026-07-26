"""
Local Whisper STT (offline fallback path)
==========================================
Not currently imported anywhere in the live request pipeline — the
production STT path is the browser's own Web Speech API (see
frontend/react/src/hooks/useVoice.js, useWakeWord.js). This module exists
as an alternative offline/local transcription path.

Two things fixed here as part of the v1.1 performance foundation pass:

1. print() -> logger. Scattered print() statements don't respect log
   levels, don't get the request Trace ID, and don't go through the
   centralized logging setup the rest of the codebase uses.

2. Lazy model loading. The Whisper model used to load at IMPORT TIME
   (module-level `WhisperModel(...)` instantiation) — meaning simply
   importing this file, even without ever calling listen(), paid the full
   model-load cost. Since this module isn't currently wired into startup,
   that cost isn't being paid today, but the moment someone re-enables
   this path by adding an import, startup would silently become slow
   again with no obvious cause. Loading now happens on first actual use
   (get_model()), cached after that — "keep critical modules warm, lazy-
   load optional ones" applied literally: this module is optional, so it
   shouldn't cost anything until it's actually used.
"""

from __future__ import annotations

import sounddevice as sd
from scipy.io.wavfile import write

from utils.logger import get_logger

logger = get_logger(__name__)

_model = None


def get_model():
    """Lazily load and cache the Whisper model on first real use."""
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        logger.info("Loading Whisper model...")
        _model = WhisperModel("base", device="cpu", compute_type="int8")
        logger.info("Whisper model loaded.")
    return _model


def listen(seconds: int = 6) -> str:
    fs = 16000

    logger.info("Listening... speak now.")

    recording = sd.rec(int(seconds * fs), samplerate=fs, channels=1, dtype="int16")
    sd.wait()

    logger.debug("Recording finished.")

    write("input.wav", fs, recording)

    logger.debug("Transcribing...")

    model = get_model()
    segments, info = model.transcribe(
        "input.wav",
        language="en",  # Indian English works better
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )

    text = "".join(segment.text + " " for segment in segments).strip()

    logger.debug("Detected language: %s", info.language)

    if len(text) < 2:
        return ""

    return text


if __name__ == "__main__":
    result = listen()
    logger.info("You said: %s", result)