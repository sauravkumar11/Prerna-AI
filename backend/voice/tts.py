"""
TTS — Text to Speech
====================
Uses edge-tts (Microsoft Neural TTS, free, no API key needed).

Temp files are created per request and ALWAYS deleted after the caller
is done — previously they accumulated in the OS temp folder indefinitely.
The /tts route now streams the bytes and deletes the file in a finally block.
"""

from __future__ import annotations

import asyncio
import os
import re
import tempfile

import edge_tts

from utils.logger import get_logger
from voice.speech_naturalizer import naturalize, SpeechChunk

logger = get_logger(__name__)

VOICE = "en-IN-NeerjaNeural"

EMOTION_STYLES: dict[str, dict[str, str]] = {
    "EXCITED":   {"rate": "+20%", "pitch": "+15Hz"},
    "PLAYFUL":   {"rate": "+10%", "pitch": "+10Hz"},
    "CARING":    {"rate": "-10%", "pitch": "-5Hz"},
    "SAD":       {"rate": "-20%", "pitch": "-10Hz"},
    "ANGRY":     {"rate": "+15%", "pitch": "+20Hz"},
    "SHY":       {"rate": "-15%", "pitch": "+5Hz"},
    "SURPRISED": {"rate": "+25%", "pitch": "+15Hz"},
    "CALM":      {"rate": "+0%",  "pitch": "+0Hz"},
}

_PERCENT_RE = re.compile(r"([+-]?\d+)%")
_HZ_RE = re.compile(r"([+-]?\d+)Hz", re.I)


def _parse_percent(value: str) -> int:
    m = _PERCENT_RE.search(value)
    return int(m.group(1)) if m else 0


def _parse_hz(value: str) -> int:
    m = _HZ_RE.search(value)
    return int(m.group(1)) if m else 0


async def _synthesize_bytes(text: str, rate: str, pitch: str) -> bytes:
    """Lowest-level primitive: one edge-tts call, explicit rate/pitch
    strings, returns raw mp3 bytes with the temp file always cleaned up."""
    fd, filename = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        communicate = edge_tts.Communicate(text=text, voice=VOICE, rate=rate, pitch=pitch)
        await communicate.save(filename)
        with open(filename, "rb") as f:
            return f.read()
    finally:
        try:
            os.unlink(filename)
        except OSError:
            pass


async def generate_audio(text: str, emotion: str = "CALM") -> str:
    """Generate a TTS audio file for the WHOLE text as one call (no
    per-sentence rhythm variation). Returns the temp file path.

    Kept for callers that specifically want a single file on disk rather
    than bytes — generate_audio_bytes() below is preferred for the API
    route and applies the naturalizer.
    """
    settings = EMOTION_STYLES.get(emotion.upper(), EMOTION_STYLES["CALM"])

    fd, filename = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)

    try:
        communicate = edge_tts.Communicate(
            text=text,
            voice=VOICE,
            rate=settings["rate"],
            pitch=settings["pitch"],
        )
        await communicate.save(filename)
        logger.debug("TTS generated: %s (%s)", filename, emotion)
        return filename
    except Exception:
        # Clean up immediately on failure so we don't leave an empty file
        try:
            os.unlink(filename)
        except OSError:
            pass
        raise


async def generate_audio_bytes(text: str, emotion: str = "CALM") -> bytes:
    """Generate TTS and return raw bytes.

    Applies the speech naturalizer: for a genuinely multi-sentence reply,
    each sentence is synthesized with its own small rate/pitch variation
    (see voice/speech_naturalizer.py for why this — not SSML pauses/
    emphasis — is the real, honest way to get rhythm out of edge-tts) and
    all chunks are generated CONCURRENTLY via asyncio.gather, so a 3-4
    sentence reply costs roughly one network round-trip's worth of wall
    time, not three or four sequential ones.

    For a single-sentence (or empty) reply this is IDENTICAL in cost to
    the original single-call implementation — no latency regression for
    the short confirmations that make up most tool-command replies.
    """
    chunks = naturalize(text)

    if len(chunks) <= 1:
        single_text = chunks[0].text if chunks else text
        settings = EMOTION_STYLES.get(emotion.upper(), EMOTION_STYLES["CALM"])
        return await _synthesize_bytes(single_text, settings["rate"], settings["pitch"])

    base = EMOTION_STYLES.get(emotion.upper(), EMOTION_STYLES["CALM"])
    base_rate = _parse_percent(base["rate"])
    base_pitch = _parse_hz(base["pitch"])

    async def _render(chunk: SpeechChunk) -> bytes:
        rate = f"{base_rate + chunk.rate_delta:+d}%"
        pitch = f"{base_pitch + chunk.pitch_delta:+d}Hz"
        return await _synthesize_bytes(chunk.text, rate, pitch)

    try:
        parts = await asyncio.gather(*(_render(c) for c in chunks))
    except Exception:
        # If per-chunk generation fails for any reason (network hiccup on
        # one of several concurrent calls, etc.), fall back to a single
        # whole-text call rather than surfacing a broken multi-part
        # request — same net behavior as before this feature existed.
        logger.warning("Per-chunk TTS generation failed — falling back to single-call synthesis.", exc_info=True)
        settings = EMOTION_STYLES.get(emotion.upper(), EMOTION_STYLES["CALM"])
        return await _synthesize_bytes(text, settings["rate"], settings["pitch"])

    logger.debug("TTS generated %d chunk(s) concurrently (%s)", len(parts), emotion)
    return b"".join(parts)