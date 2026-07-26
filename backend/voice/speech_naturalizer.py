"""
Speech Naturalizer
===================
IMPORTANT CONSTRAINT THIS MODULE WORKS AROUND:
Edge TTS (the engine Prerna uses) does not support custom SSML — Microsoft
strips anything beyond a single <voice><prosody> pair server-side. That
rules out <break>, <emphasis>, <say-as>, and <mstts:express-as> entirely;
they are simply not achievable with this TTS engine, not a matter of
effort. This module gets real pacing/rhythm variation a different way:
splitting a reply into sentence-level chunks and generating each with its
own rate/pitch (still just the two real levers edge-tts exposes), then
concatenating the audio — instead of pretending to emit pause/emphasis
markup that would be silently discarded.

Deliberately NOT doing:
  - Injecting literal filler words ("Hmm...", "Well...", "Ah...",
    "Actually..."). This was tried in the frontend as a spoken filler
    during response latency and reported back as sounding scripted/robotic
    — the fix was to remove it, not move the same pattern into the TTS
    layer. Natural-sounding pacing here comes from real sentence structure
    and rate/pitch variation, not inserted stock phrases.
  - Fake "breathing sounds" — there's no way to synthesize a believable
    breath with this engine, and a bad approximation is worse than none.
    Real sentence boundaries (see split_sentences) already give the engine
    natural places to land, without needing an audible artifact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

# Sentence-ending punctuation, avoiding splits on common abbreviations
# (Mr./Dr./approx./etc.) — not exhaustive, but covers the common cases
# without needing a full NLP sentence tokenizer as a dependency.
_ABBREVIATIONS = {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "vs", "etc", "approx", "e.g", "i.e"}
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")

_HAS_DIGIT_RE = re.compile(r"\d")
_HAS_PROPER_NOUN_RUN_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,})\b")


@dataclass
class SpeechChunk:
    text: str
    rate_delta: int = 0   # percentage points, added to the emotion's base rate
    pitch_delta: int = 0  # Hz, added to the emotion's base pitch


def clean_text(text: str) -> str:
    """Strip artifacts that shouldn't be spoken: markdown emphasis
    characters, stray double spaces/newlines, leftover bracket tags. Safe
    to run on already-clean text — every substitution is a no-op if the
    pattern isn't present."""
    if not text:
        return ""

    cleaned = text
    # Markdown emphasis characters read awkwardly if spoken literally by
    # some engines, and add no value here since edge-tts can't act on them.
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"_{1,2}([^_]+)_{1,2}", r"\1", cleaned)
    # Collapse accidental double punctuation/whitespace from text assembly.
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"\.{4,}", "...", cleaned)
    return cleaned.strip()


def split_sentences(text: str) -> List[str]:
    """Split into sentence-level chunks on real terminators, giving the
    engine genuine sentence boundaries — the actual mechanism edge-tts's
    underlying neural model uses for natural pausing, since it can't be
    told to pause any other way. Guards against splitting on the handful
    of common abbreviations that end in a period without ending a
    sentence."""
    if not text:
        return []

    raw_parts = _SENTENCE_SPLIT_RE.split(text)
    sentences: List[str] = []
    buffer = ""

    for part in raw_parts:
        buffer = f"{buffer} {part}".strip() if buffer else part
        last_word = re.sub(r"[.!?]+$", "", buffer.split()[-1] if buffer.split() else "").lower()
        if last_word in _ABBREVIATIONS:
            continue  # don't treat this as a sentence end — keep accumulating
        sentences.append(buffer)
        buffer = ""

    if buffer:
        sentences.append(buffer)

    return [s.strip() for s in sentences if s.strip()]


def _chunk_deltas(sentence: str, index: int, total: int) -> tuple[int, int]:
    """The honest, whole-sentence-granularity approximation of 'emphasis'
    and 'rhythm' available without word-level SSML: slow down slightly for
    sentences carrying a number or a multi-word proper-noun run (names,
    specific things worth landing on clearly), keep short confirmations at
    normal pace rather than artificially varying everything."""
    words = sentence.split()

    if len(words) <= 3:
        return 0, 0  # short confirmations ("Done.", "Got it.") — no change

    rate_delta = 0
    if _HAS_DIGIT_RE.search(sentence) or _HAS_PROPER_NOUN_RUN_RE.search(sentence):
        rate_delta -= 6  # slightly slower — the closest honest stand-in for emphasis

    # The final sentence of a longer reply often lands the actual point or
    # a question — a touch slower reads as more deliberate/conversational
    # rather than trailing off at the same clipped pace as the rest.
    if total > 1 and index == total - 1 and len(words) > 4:
        rate_delta -= 3

    return rate_delta, 0


def naturalize(text: str) -> List[SpeechChunk]:
    """Full pipeline: clean -> split -> per-chunk rate/pitch deltas.
    Returns [] for empty input. A single-sentence reply still goes through
    this (returns one chunk with delta 0,0) so callers don't need a
    separate short-circuit — the caller decides whether multi-chunk
    generation is worth it based on len(chunks)."""
    cleaned = clean_text(text)
    if not cleaned:
        return []

    sentences = split_sentences(cleaned)
    if not sentences:
        return [SpeechChunk(text=cleaned)]

    chunks = []
    for i, sentence in enumerate(sentences):
        rate_delta, pitch_delta = _chunk_deltas(sentence, i, len(sentences))
        chunks.append(SpeechChunk(text=sentence, rate_delta=rate_delta, pitch_delta=pitch_delta))
    return chunks