"""Tests for agent/executor.py aligned to current reasoning/validation flow."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from agent.executor import execute_plan, execute_step
from agent.registry import ToolAction, ToolResult
from agent.validation import ValidationResult


def _outcome(*, ok: bool = True, tool: str = "system", action_name: str = "lock", action: ToolAction | None = None):
    return SimpleNamespace(
        ok=ok,
        rationale="",
        tool_name=tool,
        action_name=action_name,
        action=action,
        error_message=None if ok else "failed",
    )


def test_execute_step_success_calls_handler_and_logs_activity():
    tool_action = ToolAction(name="lock", handler=lambda **_: ToolResult(True, "ok"), required_args=[])

    with patch("agent.executor.reason", return_value=_outcome(action=tool_action)), patch(
        "agent.executor.validate", return_value=ValidationResult(ok=True)
    ), patch("agent.executor.run_with_verification", return_value=(ToolResult(True, "done"), True)) as run_verify, patch(
        "agent.executor.log_activity"
    ) as log_activity, patch("agent.executor.session.update_from_action") as update_from_action:
        result = execute_step({"tool": "system", "args": {"action": "lock"}})

    assert result.success is True
    run_verify.assert_called_once()
    log_activity.assert_called_once()
    update_from_action.assert_called_once()


def test_execute_step_requires_confirmation_when_validation_demands_it():
    tool_action = ToolAction(name="shutdown", handler=lambda **_: ToolResult(True, "ok"), required_args=[], dangerous=True)
    validation = ValidationResult(ok=False, needs_confirmation=True, error_message="confirm")

    with patch("agent.executor.reason", return_value=_outcome(action_name="shutdown", action=tool_action)), patch(
        "agent.executor.validate", return_value=validation
    ):
        result = execute_step({"tool": "system", "args": {"action": "shutdown"}}, confirmed=False)

    assert result.success is False
    assert result.data["requires_confirmation"] is True
    assert result.data["tool"] == "system"


def test_execute_plan_stops_after_first_failure():
    with patch("agent.executor.execute_step") as execute_step_mock:
        execute_step_mock.side_effect = [ToolResult(False, "first failed"), ToolResult(True, "second ok")]
        result = execute_plan(
            [
                {"tool": "system", "args": {"action": "lock"}},
                {"tool": "system", "args": {"action": "sleep"}},
            ]
        )

    assert result.success is False
    assert execute_step_mock.call_count == 1


def test_execute_plan_chat_only_returns_chat_result():
    result = execute_plan([{"tool": "chat", "args": {}}])
    assert result.success is True
    assert result.data == {"is_chat": True}


def test_execute_plan_returns_confirmation_result_without_running_later_steps():
    confirmation = ToolResult(
        False,
        "confirm",
        data={"requires_confirmation": True, "tool": "system", "action": "shutdown", "step": {}},
    )

    with patch("agent.executor.execute_step", return_value=confirmation) as execute_step_mock:
        result = execute_plan(
            [
                {"tool": "system", "args": {"action": "shutdown"}},
                {"tool": "system", "args": {"action": "sleep"}},
            ]
        )

    assert result is confirmation
    execute_step_mock.assert_called_once()
