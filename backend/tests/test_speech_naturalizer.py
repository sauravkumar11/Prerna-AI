# -*- coding: utf-8 -*-
"""
Tests for voice/speech_naturalizer.py

Covers the three pure-logic pieces this module is responsible for:
1. clean_text() — markdown/whitespace cleanup, safe to run on already-clean text.
2. split_sentences() — real sentence boundaries, correctly guarding against
   splitting on common abbreviations (Dr./Mr./etc.).
3. naturalize() — the honest, whole-sentence-granularity approximation of
   "emphasis" and "rhythm" (see the module's own docstring for why this,
   not SSML, is the real approach given Edge TTS blocks custom SSML).
"""

from __future__ import annotations

from voice.speech_naturalizer import clean_text, split_sentences, naturalize, SpeechChunk


# ── clean_text ──────────────────────────────────────────────────────────────

def test_clean_text_strips_markdown_bold():
    assert clean_text("**bold**") == "bold"


def test_clean_text_strips_markdown_italic_underscore():
    assert clean_text("_italic_") == "italic"


def test_clean_text_strips_markdown_asterisk_italic():
    assert clean_text("*italic*") == "italic"


def test_clean_text_collapses_extra_spaces():
    assert clean_text("hello    world") == "hello world"


def test_clean_text_collapses_excessive_ellipsis():
    assert clean_text("wait......") == "wait..."


def test_clean_text_empty_input():
    assert clean_text("") == ""


def test_clean_text_none_safe_input_is_falsy():
    assert clean_text(None) == ""


def test_clean_text_is_idempotent_on_already_clean_text():
    text = "This is already clean."
    assert clean_text(text) == text


# ── split_sentences ──────────────────────────────────────────────────────────

def test_split_sentences_basic_two_sentences():
    result = split_sentences("I opened Chrome. It should be visible now.")
    assert result == ["I opened Chrome.", "It should be visible now."]


def test_split_sentences_guards_against_abbreviation_false_split():
    """'Dr.' must not be treated as a sentence boundary."""
    result = split_sentences("Dr. Sharma called. He wants a meeting tomorrow.")
    assert result == ["Dr. Sharma called.", "He wants a meeting tomorrow."]


def test_split_sentences_single_sentence_no_split():
    result = split_sentences("Just one sentence here")
    assert result == ["Just one sentence here"]


def test_split_sentences_empty_input():
    assert split_sentences("") == []


def test_split_sentences_question_and_exclamation():
    result = split_sentences("Really? That's amazing!")
    assert len(result) == 2
    assert result[0].endswith("?")
    assert result[1].endswith("!")


# ── naturalize (full pipeline) ───────────────────────────────────────────────

def test_naturalize_empty_text_returns_no_chunks():
    assert naturalize("") == []


def test_naturalize_short_reply_no_rate_delta():
    """Short confirmations ('Done.') shouldn't get artificial rate
    variation — nothing meaningful to emphasize."""
    chunks = naturalize("Done.")
    assert len(chunks) == 1
    assert chunks[0].rate_delta == 0
    assert chunks[0].pitch_delta == 0


def test_naturalize_sentence_with_number_gets_slowdown():
    """The honest 'emphasis' approximation: a sentence containing a
    number is slowed down slightly rather than word-level pitch-boosted
    (which Edge TTS doesn't support)."""
    chunks = naturalize("I found three important emails from Rohan Sharma.")
    assert chunks[0].rate_delta < 0


def test_naturalize_multi_sentence_reply_produces_multiple_chunks():
    chunks = naturalize("I found three important emails from Rohan Sharma. Should I open them now?")
    assert len(chunks) == 2
    assert chunks[0].text == "I found three important emails from Rohan Sharma."
    assert chunks[1].text == "Should I open them now?"


def test_naturalize_final_sentence_of_longer_reply_gets_slight_slowdown():
    chunks = naturalize("Here is the plan for today. First we open the editor. Then we run the tests.")
    assert len(chunks) == 3
    # Last sentence gets an additional deliberate-pacing delta on top of
    # whatever its own content triggers.
    assert chunks[-1].rate_delta <= 0


def test_naturalize_single_long_sentence_with_no_number_or_name_run_unchanged():
    chunks = naturalize("I already opened Chrome and started playing your song for you.")
    assert len(chunks) == 1
    assert chunks[0].rate_delta == 0


def test_naturalize_returns_speech_chunk_instances():
    chunks = naturalize("Hello there. How are you?")
    assert all(isinstance(c, SpeechChunk) for c in chunks)