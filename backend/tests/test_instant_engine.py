# -*- coding: utf-8 -*-
"""
Tests for agent/instant_engine.py

These convert the manual verification done while building the Tier-0
Instant Engine into permanent regression tests. Two properties matter most
and get the heaviest coverage:

1. POSITIVE matches produce a plan step that actually passes real
   validation (agent.reasoning.reason) — a match that can't validate would
   be worse than no match at all.
2. NEGATIVE matches (ambiguous/compound requests) correctly return None —
   this is the safety property of the whole module: a false positive here
   would silently change what a command does, not just how fast it runs.
"""

from __future__ import annotations

import tools  # noqa: F401 - registers every real tool via conftest stubs
from agent.instant_engine import match, refresh_patterns
from agent.reasoning import reason


def _assert_matches_and_validates(message: str) -> dict:
    step = match(message)
    assert step is not None, f"expected a Tier-0 match for {message!r}, got None"
    outcome = reason(step)
    assert outcome.ok, f"Tier-0 step for {message!r} failed validation: {outcome.error_message}"
    return step


def _assert_no_match(message: str) -> None:
    step = match(message)
    assert step is None, f"expected NO Tier-0 match for {message!r}, got {step}"


# ── Volume ──────────────────────────────────────────────────────────────────

def test_volume_up():
    step = _assert_matches_and_validates("volume up")
    assert step == {"tool": "volume", "args": {"action": "up"}}


def test_volume_down_with_punctuation():
    step = _assert_matches_and_validates("Volume Down.")
    assert step["args"]["action"] == "down"


def test_mute():
    _assert_matches_and_validates("mute")


def test_mute_karo_hinglish():
    _assert_matches_and_validates("mute karo")


def test_unmute():
    _assert_matches_and_validates("unmute")


# ── System: lock / screenshot / shutdown / restart / sleep ─────────────────

def test_lock_bare():
    _assert_matches_and_validates("lock")


def test_lock_the_laptop():
    _assert_matches_and_validates("lock the laptop")


def test_take_a_screenshot():
    _assert_matches_and_validates("take a screenshot")


def test_screenshot_bare():
    _assert_matches_and_validates("screenshot")


def test_shut_down():
    _assert_matches_and_validates("shut down")


def test_restart_the_pc():
    _assert_matches_and_validates("restart the pc")


def test_go_to_sleep():
    _assert_matches_and_validates("go to sleep")


# ── Brightness — the one Tier-0 pattern with a real argument ───────────────

def test_brightness_to_80():
    step = _assert_matches_and_validates("brightness to 80")
    assert step["args"]["level"] == 80


def test_brightness_with_percent_sign():
    step = _assert_matches_and_validates("set brightness 45%")
    assert step["args"]["level"] == 45


def test_brightness_out_of_range_falls_through():
    """150% isn't a valid brightness — must NOT guess/clamp, must fall
    through to the planner instead."""
    _assert_no_match("brightness to 150")


def test_brightness_with_no_number_falls_through():
    _assert_no_match("brightness")


# ── Clipboard ────────────────────────────────────────────────────────────────

def test_read_clipboard():
    _assert_matches_and_validates("read the clipboard")


def test_clear_clipboard():
    _assert_matches_and_validates("clear clipboard")


# ── App opening — sourced from config.settings.WINDOWS_APPS ────────────────

def test_open_calculator():
    step = _assert_matches_and_validates("open calculator")
    assert step == {"tool": "system", "args": {"action": "open_app", "app": "calculator"}}


def test_open_explorer_bare_form_still_works():
    _assert_matches_and_validates("open explorer")


# ── Gaps found via real production logs, fixed and now regression-tested ───

def test_open_whatsapp():
    step = _assert_matches_and_validates("open whatsapp")
    assert step == {"tool": "whatsapp", "args": {"action": "open"}}


def test_open_whatsapp_with_punctuation():
    _assert_matches_and_validates("Open WhatsApp.")


def test_open_file_explorer():
    """'file explorer' (what people actually say) wasn't matched by the
    bare 'explorer' WINDOWS_APPS pattern before this was added — was
    falling through to the planner for something entirely unambiguous."""
    step = _assert_matches_and_validates("open file explorer")
    assert step["args"]["app"] == "explorer"


def test_open_calendar():
    """'calendar' was missing from browser_tool's _SITES dict entirely —
    every 'open calendar' needed a full Gemini round trip before this fix."""
    step = _assert_matches_and_validates("open calendar")
    assert step == {"tool": "browser", "args": {"action": "open_site", "site": "calendar"}}


# ── Sites — sourced from tools.browser_tool._SITES ──────────────────────────

def test_open_youtube():
    step = _assert_matches_and_validates("open youtube")
    assert step["args"]["site"] == "youtube"


def test_open_gmail():
    _assert_matches_and_validates("open gmail")


def test_open_github():
    _assert_matches_and_validates("open the github")


def test_open_chatgpt():
    _assert_matches_and_validates("open chatgpt")


# ── Negative cases — the safety property: must NOT match ambiguous input ───

def test_play_song_is_not_tier0():
    """Needs search-query construction — genuinely needs the planner."""
    _assert_no_match("play dilbar song")


def test_message_contact_is_not_tier0():
    """Needs fuzzy contact-name resolution — genuinely needs the planner."""
    _assert_no_match("message varsha di")


def test_compound_open_and_play_is_not_tier0():
    _assert_no_match("open youtube and play dilbar song")


def test_compound_whatsapp_and_message_is_not_tier0():
    _assert_no_match("open whatsapp and message rahul")


def test_lock_word_inside_unrelated_sentence_is_not_tier0():
    """Contains the literal word 'lock' but is not the system-lock intent
    — this is the exact kind of false positive Tier 0 must never produce."""
    _assert_no_match("lock rahul out of the group")


def test_emotional_conversation_is_not_tier0():
    _assert_no_match("i cracked the interview")


def test_empty_message_is_not_tier0():
    _assert_no_match("")


def test_whitespace_only_message_is_not_tier0():
    _assert_no_match("   ")


# ── Cache/refresh behavior ───────────────────────────────────────────────────

def test_refresh_patterns_does_not_break_matching():
    """refresh_patterns() clears the cached pattern list; the next match()
    call must rebuild it correctly rather than erroring or losing coverage."""
    assert match("volume up") is not None
    refresh_patterns()
    assert match("volume up") is not None