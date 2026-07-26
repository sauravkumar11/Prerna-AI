# -*- coding: utf-8 -*-
"""Tests for agent.verification.window_title_absent — the negated
verifier added for close/stop-style actions (e.g. camera.close), since the
existing window_title_contains only handled the "is it open" direction."""

from unittest.mock import patch

import agent.verification as verification


def test_true_when_window_confirmed_gone():
    with patch.object(verification, "window_title_contains", return_value=lambda a, r: False):
        verify = verification.window_title_absent("camera")
        assert verify({}, None) is True


def test_false_when_window_still_present():
    with patch.object(verification, "window_title_contains", return_value=lambda a, r: True):
        verify = verification.window_title_absent("camera")
        assert verify({}, None) is False


def test_none_when_underlying_check_cannot_run():
    with patch.object(verification, "window_title_contains", return_value=lambda a, r: None):
        verify = verification.window_title_absent("camera")
        assert verify({}, None) is None


def test_any_of_combinator_true_if_any_true():
    always_true = lambda a, r: True
    always_false = lambda a, r: False
    combined = verification.any_of(always_false, always_true)
    assert combined({}, None) is True


def test_any_of_combinator_false_only_if_all_false():
    always_false = lambda a, r: False
    combined = verification.any_of(always_false, always_false)
    assert combined({}, None) is False


def test_any_of_combinator_none_on_mixed_signal():
    always_false = lambda a, r: False
    unknown = lambda a, r: None
    combined = verification.any_of(always_false, unknown)
    assert combined({}, None) is None


def test_run_with_verification_retries_on_definite_false_then_succeeds():
    calls = {"n": 0}

    def flaky_call():
        calls["n"] += 1
        from agent.registry import ToolResult
        return ToolResult(True, "did something")

    verify_results = iter([False, True])  # fails verification once, then confirms
    def verify(args, result):
        return next(verify_results)

    result, verified = verification.run_with_verification(
        call=flaky_call, verify=verify, args={}, max_retries=1, retry_delay=0,
    )
    assert calls["n"] == 2  # retried once
    assert verified is True


def test_run_with_verification_gives_up_after_max_retries_exhausted():
    from agent.registry import ToolResult
    result, verified = verification.run_with_verification(
        call=lambda: ToolResult(True, "did something"),
        verify=lambda args, result: False,  # always fails verification
        args={}, max_retries=2, retry_delay=0,
    )
    assert verified is False  # honestly reports it never confirmed, no infinite loop
