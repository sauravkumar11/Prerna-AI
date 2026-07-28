# -*- coding: utf-8 -*-
"""
Tests for tools/whatsapp_tool.py

This is the module with a CONFIRMED real production crash this session:
whatsapp_actions.py's functions all return (success, message) tuples, but
every wrapper in whatsapp_tool.py was doing `ToolResult(True, _action(...))`
— hardcoding success=True and passing the WHOLE TUPLE as the message
string. That crashed executor.py's `" ".join(messages)` the moment any
WhatsApp action ran.

Every action wrapper is tested here for the same two properties:
1. ToolResult.message is always a plain str (never a tuple) — this is
   the exact thing that crashed.
2. ToolResult.success correctly reflects the underlying action's real
   success/failure, not a hardcoded True regardless of outcome (a second,
   quieter bug in the same family — failures were being silently reported
   as successes before this was fixed).
"""

from __future__ import annotations

import unittest.mock as mock

import tools.whatsapp_tool as wt


def _assert_honest_result(result, expected_success: bool, expected_message: str) -> None:
    assert isinstance(result.message, str), (
        f"ToolResult.message must be a str, got {type(result.message).__name__}: {result.message!r} "
        "(this is the exact bug that crashed executor.py's ' '.join(messages))"
    )
    assert result.success == expected_success
    assert result.message == expected_message


def test_open_reproduces_and_fixes_the_original_crash():
    """The exact scenario from the production log: WhatsApp took too long
    to appear, open_whatsapp() returns (False, <message>). Must not crash
    when the result is later joined with other messages, and must report
    the real failure honestly instead of the old hardcoded True."""
    with mock.patch(
        "tools.whatsapp_tool._open_whatsapp",
        return_value=(False, "Opened WhatsApp, but it took too long to appear. Please check if WhatsApp Desktop is installed."),
    ):
        result = wt.open_whatsapp()
        _assert_honest_result(
            result, False,
            "Opened WhatsApp, but it took too long to appear. Please check if WhatsApp Desktop is installed.",
        )

    # Reproduce the EXACT executor.py code path that crashed in production —
    # this must not raise.
    messages = []
    if result.message:
        messages.append(result.message)
    joined = " ".join(messages)  # TypeError here was the original crash
    assert "took too long" in joined


def test_open_success_case():
    with mock.patch("tools.whatsapp_tool._open_whatsapp", return_value=(True, "WhatsApp is open.")):
        result = wt.open_whatsapp()
        _assert_honest_result(result, True, "WhatsApp is open.")


def test_send_message_unpacks_tuple_correctly():
    with mock.patch("tools.whatsapp_tool._send_message", return_value=(True, "Message sent to Rahul.")):
        result = wt.send_message("Rahul", "hi")
        _assert_honest_result(result, True, "Message sent to Rahul.")


def test_send_message_honest_failure():
    with mock.patch("tools.whatsapp_tool._send_message", return_value=(False, "WhatsApp lost focus while trying to message Rahul.")):
        result = wt.send_message("Rahul", "hi")
        _assert_honest_result(result, False, "WhatsApp lost focus while trying to message Rahul.")


def test_voice_call_unpacks_tuple_correctly():
    with mock.patch("tools.whatsapp_tool._voice_call", return_value=(True, "Voice call started with Rahul.")):
        result = wt.voice_call("Rahul")
        _assert_honest_result(result, True, "Voice call started with Rahul.")


def test_video_call_unpacks_tuple_correctly():
    with mock.patch("tools.whatsapp_tool._video_call", return_value=(False, "Couldn't find the video call button.")):
        result = wt.video_call("Rahul")
        _assert_honest_result(result, False, "Couldn't find the video call button.")


def test_archive_chat_unpacks_tuple_correctly():
    with mock.patch("tools.whatsapp_tool._archive_chat", return_value=(True, "Archived the chat with Rahul.")):
        result = wt.archive_chat("Rahul")
        _assert_honest_result(result, True, "Archived the chat with Rahul.")


def test_unarchive_chat_unpacks_tuple_correctly():
    with mock.patch("tools.whatsapp_tool._unarchive_chat", return_value=(True, "Unarchived the chat with Rahul.")):
        result = wt.unarchive_chat("Rahul")
        _assert_honest_result(result, True, "Unarchived the chat with Rahul.")


def test_mute_unpacks_tuple_correctly():
    with mock.patch("tools.whatsapp_tool._mute_contact", return_value=(True, "Muted notifications from Rahul.")):
        result = wt.mute("Rahul")
        _assert_honest_result(result, True, "Muted notifications from Rahul.")


def test_delete_chat_unpacks_tuple_correctly():
    with mock.patch("tools.whatsapp_tool._delete_chat", return_value=(True, "Deleted the chat with Rahul.")):
        result = wt.delete_chat("Rahul")
        _assert_honest_result(result, True, "Deleted the chat with Rahul.")


def test_mark_as_read_unpacks_tuple_correctly():
    with mock.patch("tools.whatsapp_tool._mark_as_read", return_value=(True, "Marked the chat with Rahul as read.")):
        result = wt.mark_as_read("Rahul")
        _assert_honest_result(result, True, "Marked the chat with Rahul as read.")


def test_mark_as_unread_unpacks_tuple_correctly():
    with mock.patch("tools.whatsapp_tool._mark_as_unread", return_value=(True, "Marked the chat with Rahul as unread.")):
        result = wt.mark_as_unread("Rahul")
        _assert_honest_result(result, True, "Marked the chat with Rahul as unread.")


def test_block_unpacks_tuple_correctly():
    with mock.patch("tools.whatsapp_tool._block_contact", return_value=(True, "Blocked Rahul.")):
        result = wt.block("Rahul")
        _assert_honest_result(result, True, "Blocked Rahul.")


def test_unblock_unpacks_tuple_correctly():
    with mock.patch("tools.whatsapp_tool._unblock_contact", return_value=(True, "Unblocked Rahul.")):
        result = wt.unblock("Rahul")
        _assert_honest_result(result, True, "Unblocked Rahul.")


def test_pin_chat_unpacks_tuple_correctly():
    with mock.patch("tools.whatsapp_tool._pin_chat", return_value=(True, "Pinned the chat with Rahul.")):
        result = wt.pin_chat("Rahul")
        _assert_honest_result(result, True, "Pinned the chat with Rahul.")


def test_unpin_chat_unpacks_tuple_correctly():
    with mock.patch("tools.whatsapp_tool._unpin_chat", return_value=(True, "Unpinned the chat with Rahul.")):
        result = wt.unpin_chat("Rahul")
        _assert_honest_result(result, True, "Unpinned the chat with Rahul.")


def test_open_chat_success():
    with mock.patch("tools.whatsapp_tool._open_whatsapp", return_value=(True, "WhatsApp is open.")), \
         mock.patch("tools.whatsapp_tool._search_contact", return_value=True):
        result = wt.open_chat("Rahul")
        assert result.success is True
        assert isinstance(result.message, str)


def test_open_chat_reports_honest_failure_when_contact_not_found():
    """search_contact() returning False (not found) must be surfaced as a
    real failure, not silently reported as success."""
    with mock.patch("tools.whatsapp_tool._open_whatsapp", return_value=(True, "WhatsApp is open.")), \
         mock.patch("tools.whatsapp_tool._search_contact", return_value=False):
        result = wt.open_chat("NonexistentContact")
        assert result.success is False
        assert "couldn't find" in result.message.lower() or "could not find" in result.message.lower()


def test_open_chat_propagates_whatsapp_open_failure():
    with mock.patch("tools.whatsapp_tool._open_whatsapp", return_value=(False, "WhatsApp took too long to appear.")):
        result = wt.open_chat("Rahul")
        assert result.success is False
        assert isinstance(result.message, str)