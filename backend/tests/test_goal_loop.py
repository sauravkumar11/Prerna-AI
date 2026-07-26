# -*- coding: utf-8 -*-
"""Tests for agent.goal_loop.run_goal — formalizes the 5 behavioral
guarantees validated by hand during development: no wasted retries on
success, real retry-with-context on failure, confirmation gates are NEVER
auto-bypassed, chat needs no retry, and exhaustion returns an honest
failure rather than a fabricated success."""

from unittest.mock import patch

from agent.registry import ToolResult
import agent.goal_loop as goal_loop


def test_succeeds_on_first_attempt_without_retrying():
    with patch.object(goal_loop, "plan", return_value=[{"tool": "x", "args": {}}]) as m_plan, \
         patch.object(goal_loop, "execute_plan", return_value=ToolResult(True, "done")):
        result = goal_loop.run_goal("do x", None, {}, [], None, None)
        assert result.success and result.message == "done"
        assert m_plan.call_count == 1


def test_retries_with_growing_failure_context_then_succeeds():
    seen_messages = []

    def fake_plan(msg, *a, **kw):
        seen_messages.append(msg)
        return [{"tool": "x", "args": {}}]

    results = iter([
        ToolResult(False, "boom"),
        ToolResult(False, "boom again"),
        ToolResult(True, "finally worked"),
    ])

    with patch.object(goal_loop, "plan", side_effect=fake_plan), \
         patch.object(goal_loop, "execute_plan", side_effect=lambda *a, **k: next(results)):
        result = goal_loop.run_goal("do y", None, {}, [], None, None, max_iterations=3)

    assert result.success and result.message == "finally worked"
    assert len(seen_messages) == 3
    assert "retry" in seen_messages[1].lower() and "boom" in seen_messages[1]


def test_pure_chat_returns_immediately_no_retry():
    with patch.object(goal_loop, "plan", return_value=[{"tool": "chat", "args": {}}]) as m_plan, \
         patch.object(goal_loop, "execute_plan",
                       return_value=ToolResult(True, "", data={"is_chat": True})):
        result = goal_loop.run_goal("hows it going", None, {}, [], None, None)
        assert result.data.get("is_chat") is True
        assert m_plan.call_count == 1


def test_confirmation_gate_is_never_auto_retried():
    # Safety-critical: a bounded retry loop must NEVER auto-confirm a
    # dangerous action just because it has attempts left.
    with patch.object(goal_loop, "plan",
                       return_value=[{"tool": "system", "args": {"action": "shutdown"}}]) as m_plan, \
         patch.object(goal_loop, "execute_plan",
                       return_value=ToolResult(False, "Are you sure?", data={"requires_confirmation": True})):
        result = goal_loop.run_goal("shutdown", None, {}, [], None, None)
        assert result.data.get("requires_confirmation") is True
        assert m_plan.call_count == 1


def test_exhausted_retries_return_honest_final_failure_not_fake_success():
    with patch.object(goal_loop, "plan", return_value=[{"tool": "x", "args": {}}]) as m_plan, \
         patch.object(goal_loop, "execute_plan", return_value=ToolResult(False, "still broken")):
        result = goal_loop.run_goal("do z", None, {}, [], None, None, max_iterations=3)
        assert not result.success
        assert result.message == "still broken"
        assert m_plan.call_count == 3


def test_confirmed_flag_is_passed_through_to_execute_plan():
    captured = {}

    def fake_execute_plan(steps, confirmed=False):
        captured["confirmed"] = confirmed
        return ToolResult(True, "done")

    with patch.object(goal_loop, "plan", return_value=[{"tool": "x", "args": {}}]), \
         patch.object(goal_loop, "execute_plan", side_effect=fake_execute_plan):
        goal_loop.run_goal("do x", None, {}, [], None, None, confirmed=True)

    assert captured["confirmed"] is True
