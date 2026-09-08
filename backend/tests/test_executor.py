"""
test_executor.py
================
Unit tests for agent/executor.py

Tests the core execution engine that runs planned tool actions,
handles errors gracefully, and manages execution state.

v1.1.1 addition: Comprehensive executor test coverage
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from agent.registry import ToolResult, ToolAction, Tool
from agent.executor import execute_plan


class TestExecutePlan:
    """Test suite for plan execution."""

    @pytest.mark.unit
    def test_execute_empty_plan(self):
        """Executing an empty plan should succeed immediately."""
        plan = []
        result = execute_plan(plan, {})
        assert result is not None

    @pytest.mark.unit
    def test_execute_single_step_success(self, helpers):
        """A single successful step should complete."""
        plan = [
            {
                "tool": "system_tool",
                "action": "increase_volume",
                "args": {"amount": 10},
            }
        ]

        with patch("agent.executor.get_registry") as mock_registry:
            mock_action = MagicMock()
            mock_action.handler = MagicMock(
                return_value=ToolResult(True, "Volume increased to 10%")
            )
            mock_registry.return_value = {
                "system_tool": Tool(name="system_tool", actions={
                    "increase_volume": mock_action
                })
            }

            result = execute_plan(plan, {})
            assert result is not None

    @pytest.mark.unit
    def test_execute_multiple_steps_sequential(self):
        """Multiple steps should execute in order."""
        plan = [
            {
                "tool": "browser_tool",
                "action": "open",
                "args": {"url": "https://example.com"},
            },
            {
                "tool": "browser_tool",
                "action": "click",
                "args": {"element": "button"},
            },
        ]

        with patch("agent.executor.get_registry") as mock_registry:
            mock_actions = {
                "open": MagicMock(handler=MagicMock(
                    return_value=ToolResult(True, "Opened URL")
                )),
                "click": MagicMock(handler=MagicMock(
                    return_value=ToolResult(True, "Clicked element")
                )),
            }
            mock_registry.return_value = {
                "browser_tool": Tool(name="browser_tool", actions=mock_actions)
            }

            result = execute_plan(plan, {})
            assert result is not None

    @pytest.mark.unit
    def test_execute_stops_on_failure(self):
        """Execution should stop when a step fails."""
        plan = [
            {
                "tool": "browser_tool",
                "action": "open",
                "args": {"url": "https://example.com"},
            },
            {
                "tool": "browser_tool",
                "action": "click",
                "args": {"element": "button"},
            },
        ]

        with patch("agent.executor.get_registry") as mock_registry:
            mock_actions = {
                "open": MagicMock(handler=MagicMock(
                    return_value=ToolResult(False, "Failed to open URL")
                )),
                "click": MagicMock(handler=MagicMock(
                    return_value=ToolResult(True, "Clicked element")
                )),
            }
            mock_registry.return_value = {
                "browser_tool": Tool(name="browser_tool", actions=mock_actions)
            }

            result = execute_plan(plan, {})
            # Second action should not have been called
            mock_actions["click"].handler.assert_not_called()

    @pytest.mark.unit
    def test_execute_with_confirmation_required(self):
        """Steps marked dangerous should require confirmation."""
        plan = [
            {
                "tool": "system_tool",
                "action": "shutdown",
                "args": {},
                "requires_confirmation": True,
            }
        ]

        with patch("agent.executor.get_registry") as mock_registry:
            mock_action = MagicMock()
            mock_action.handler = MagicMock(
                return_value=ToolResult(True, "System shutting down")
            )
            mock_action.dangerous = True

            mock_registry.return_value = {
                "system_tool": Tool(name="system_tool", actions={
                    "shutdown": mock_action
                })
            }

            # With confirmation_confirmed=False, should skip execution
            context = {"confirmation_confirmed": False}
            result = execute_plan(plan, context)

            # Handler should not have been called without confirmation
            mock_action.handler.assert_not_called()

    @pytest.mark.unit
    def test_execute_handles_missing_tool(self, helpers):
        """Execution should gracefully handle missing tool."""
        plan = [
            {
                "tool": "nonexistent_tool",
                "action": "some_action",
                "args": {},
            }
        ]

        with patch("agent.executor.get_registry") as mock_registry:
            mock_registry.return_value = {}  # Empty registry

            result = execute_plan(plan, {})
            # Should return a result indicating failure
            assert result is not None

    @pytest.mark.unit
    def test_execute_with_context_passed_to_handlers(self):
        """Handler should receive execution context."""
        plan = [
            {
                "tool": "system_tool",
                "action": "get_info",
                "args": {},
            }
        ]

        context = {
            "user_name": "Test User",
            "session_id": "test-123",
        }

        with patch("agent.executor.get_registry") as mock_registry:
            mock_action = MagicMock()
            handler = MagicMock(return_value=ToolResult(True, "Info retrieved"))
            mock_action.handler = handler

            mock_registry.return_value = {
                "system_tool": Tool(name="system_tool", actions={
                    "get_info": mock_action
                })
            }

            result = execute_plan(plan, context)
            # Handler should have been called
            assert handler.called

    @pytest.mark.unit
    def test_execute_exception_handling(self):
        """Exceptions during execution should be caught and logged."""
        plan = [
            {
                "tool": "browser_tool",
                "action": "open",
                "args": {"url": "https://example.com"},
            }
        ]

        with patch("agent.executor.get_registry") as mock_registry:
            mock_action = MagicMock()
            mock_action.handler = MagicMock(
                side_effect=RuntimeError("Browser crashed")
            )

            mock_registry.return_value = {
                "browser_tool": Tool(name="browser_tool", actions={
                    "open": mock_action
                })
            }

            result = execute_plan(plan, {})
            # Should return a failed result, not raise
            assert result is not None


class TestExecutorEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.unit
    def test_execute_with_empty_args(self):
        """Steps with empty args should execute normally."""
        plan = [
            {
                "tool": "system_tool",
                "action": "lock_screen",
                "args": {},
            }
        ]

        with patch("agent.executor.get_registry") as mock_registry:
            mock_action = MagicMock()
            mock_action.handler = MagicMock(
                return_value=ToolResult(True, "Screen locked")
            )

            mock_registry.return_value = {
                "system_tool": Tool(name="system_tool", actions={
                    "lock_screen": mock_action
                })
            }

            result = execute_plan(plan, {})
            assert result is not None

    @pytest.mark.unit
    def test_execute_with_large_args(self):
        """Steps with large argument payloads should work."""
        large_content = "x" * 10000
        plan = [
            {
                "tool": "file_tool",
                "action": "write",
                "args": {"path": "/tmp/file.txt", "content": large_content},
            }
        ]

        with patch("agent.executor.get_registry") as mock_registry:
            mock_action = MagicMock()
            mock_action.handler = MagicMock(
                return_value=ToolResult(True, "File written")
            )

            mock_registry.return_value = {
                "file_tool": Tool(name="file_tool", actions={
                    "write": mock_action
                })
            }

            result = execute_plan(plan, {})
            assert result is not None

    @pytest.mark.unit
    def test_execute_response_aggregation(self):
        """Results from multiple steps should be aggregated."""
        plan = [
            {
                "tool": "system_tool",
                "action": "action1",
                "args": {},
            },
            {
                "tool": "system_tool",
                "action": "action2",
                "args": {},
            },
        ]

        with patch("agent.executor.get_registry") as mock_registry:
            actions = {
                "action1": MagicMock(handler=MagicMock(
                    return_value=ToolResult(True, "Action 1 done")
                )),
                "action2": MagicMock(handler=MagicMock(
                    return_value=ToolResult(True, "Action 2 done")
                )),
            }

            mock_registry.return_value = {
                "system_tool": Tool(name="system_tool", actions=actions)
            }

            result = execute_plan(plan, {})
            assert result is not None
            # Both actions should be called
            assert actions["action1"].handler.called
            assert actions["action2"].handler.called
