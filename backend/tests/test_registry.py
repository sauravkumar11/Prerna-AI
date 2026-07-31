# -*- coding: utf-8 -*-
"""
Tests for agent/registry.py — ToolResult contract enforcement (v1.1.2)

Real production bug this closes: a tool's underlying action function
changed to return (success, message) tuples, but its ToolResult-building
wrapper still passed the whole tuple through as `message`. That crashed
deep inside execute_plan()'s `" ".join(messages)` — several call frames
away from the actual mistake, with a confusing generic TypeError.

ToolResult now validates its own fields at construction time
(__post_init__), so this class of bug fails immediately, at its true
source, with a message that names the actual problem. Critically: every
tool handler already runs inside registry.safe()'s try/except, which
converts ANY exception into a graceful failed ToolResult — so this
validation can only turn an eventual confusing crash into an immediate,
clear, still-gracefully-handled one. It cannot introduce a new failure
mode, and the tests below prove that explicitly.
"""

from __future__ import annotations

import pytest

from agent.registry import ToolResult, safe


# ── Normal usage is completely unaffected ───────────────────────────────────

def test_normal_construction_still_works():
    result = ToolResult(True, "Volume increased.")
    assert result.success is True
    assert result.message == "Volume increased."


def test_construction_with_speech_still_works():
    result = ToolResult(False, "Something failed.", speech="Failed.")
    assert result.speech == "Failed."


def test_construction_with_data_payload_still_works():
    """`data` is intentionally unconstrained (Any) — used for structured
    payloads like requires_confirmation/step/is_chat flags."""
    result = ToolResult(True, "ok", data={"is_chat": True})
    assert result.data == {"is_chat": True}


def test_str_dunder_still_returns_message():
    result = ToolResult(True, "hello")
    assert str(result) == "hello"


# ── The contract is now enforced ────────────────────────────────────────────

def test_tuple_message_raises_immediately():
    """The exact whatsapp_tool.py bug scenario, reproduced directly."""
    with pytest.raises(TypeError, match="must be a str"):
        ToolResult(True, (False, "Opened WhatsApp, but it took too long to appear."))


def test_non_bool_success_raises():
    with pytest.raises(TypeError, match="must be a bool"):
        ToolResult("yes", "some message")


def test_non_str_speech_raises():
    with pytest.raises(TypeError, match="speech"):
        ToolResult(True, "ok", speech=12345)


def test_none_speech_is_still_allowed():
    """speech is Optional[str] — None must remain valid, only a non-str
    non-None value should be rejected."""
    result = ToolResult(True, "ok", speech=None)
    assert result.speech is None


# ── The critical safety property: safe() absorbs the new error gracefully ──

def test_safe_wrapper_converts_contract_violation_into_graceful_failure():
    """This is what proves the validation can't introduce a new crash:
    a tool handler that constructs an invalid ToolResult still returns a
    normal, well-formed ToolResult to its caller — just a failed one with
    a clear diagnostic message, instead of an uncaught exception."""

    @safe
    def buggy_handler():
        return ToolResult(True, (False, "some message"))  # the exact bug pattern

    result = buggy_handler()
    assert isinstance(result, ToolResult)
    assert result.success is False
    assert "must be a str" in result.message


def test_safe_wrapper_still_handles_normal_exceptions_as_before():
    """Unrelated to the new validation — confirms existing exception
    handling in safe() is untouched."""

    @safe
    def handler_that_raises():
        raise RuntimeError("something else broke")

    result = handler_that_raises()
    assert result.success is False
    assert "something else broke" in result.message


def test_safe_wrapper_still_normalizes_plain_return_values():
    """Confirms safe()'s existing plain-value normalization (str, None)
    is unaffected by the new ToolResult validation."""

    @safe
    def returns_plain_string():
        return "just a string"

    @safe
    def returns_none():
        return None

    r1 = returns_plain_string()
    r2 = returns_none()
    assert r1.success is True and r1.message == "just a string"
    assert r2.success is True and r2.message == "Done."