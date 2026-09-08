"""
test_error_handling.py
======================
Tests for utils/error_handler.py

Tests custom exception types, error handling decorators,
and recovery strategies.

v1.1.1 addition: Comprehensive error handling tests
"""

from __future__ import annotations

import pytest
from unittest.mock import patch
from utils.error_handler import (
    PrenaError,
    ToolExecutionError,
    ValidationError,
    ConfigurationError,
    PermissionError,
    RateLimitError,
    TimeoutError,
    ResourceNotFoundError,
    ExternalServiceError,
    handle_exception,
    with_error_handling,
    catch_and_log,
    RetryStrategy,
    with_recovery,
)


class TestCustomExceptions:
    """Test custom exception types."""

    @pytest.mark.unit
    def test_prena_error_creation(self):
        """Should create PrenaError with message and code."""
        error = PrenaError("Test error", error_code="TEST_ERROR")
        assert error.message == "Test error"
        assert error.error_code == "TEST_ERROR"

    @pytest.mark.unit
    def test_prena_error_to_dict(self):
        """Should convert error to dictionary."""
        error = PrenaError("Test", error_code="CODE", details={"key": "value"})
        result = error.to_dict()

        assert result["message"] == "Test"
        assert result["error_code"] == "CODE"
        assert result["details"]["key"] == "value"

    @pytest.mark.unit
    def test_tool_execution_error(self):
        """Should create tool execution error with context."""
        error = ToolExecutionError(
            tool_name="browser_tool",
            action="open",
            message="Failed to open URL",
        )

        assert "browser_tool" in str(error)
        assert "open" in str(error)
        assert error.error_code == "TOOL_EXECUTION_ERROR"

    @pytest.mark.unit
    def test_validation_error(self):
        """Should create validation error with field info."""
        error = ValidationError(
            field="email",
            reason="Invalid format",
        )

        assert "email" in str(error)
        assert "Invalid format" in str(error)
        assert error.error_code == "VALIDATION_ERROR"

    @pytest.mark.unit
    def test_configuration_error(self):
        """Should create configuration error."""
        error = ConfigurationError(
            setting="GEMINI_API_KEY",
            reason="Not set in environment",
        )

        assert "GEMINI_API_KEY" in str(error)
        assert error.error_code == "CONFIG_ERROR"

    @pytest.mark.unit
    def test_permission_error(self):
        """Should create permission error."""
        error = PermissionError(
            operation="shutdown",
            reason="Destructive action",
        )

        assert "shutdown" in str(error)
        assert error.error_code == "PERMISSION_REQUIRED"

    @pytest.mark.unit
    def test_rate_limit_error(self):
        """Should create rate limit error with retry info."""
        error = RateLimitError(
            service="gemini_api",
            retry_after=30,
        )

        assert "gemini_api" in str(error)
        assert error.error_code == "RATE_LIMIT_EXCEEDED"

    @pytest.mark.unit
    def test_timeout_error(self):
        """Should create timeout error with duration."""
        error = TimeoutError(
            operation="browser_load",
            timeout_seconds=30.0,
        )

        assert "browser_load" in str(error)
        assert "30" in str(error)
        assert error.error_code == "TIMEOUT"

    @pytest.mark.unit
    def test_resource_not_found_error(self):
        """Should create resource not found error."""
        error = ResourceNotFoundError(
            resource_type="Task",
            resource_id="task-123",
        )

        assert "Task" in str(error)
        assert "task-123" in str(error)
        assert error.error_code == "NOT_FOUND"

    @pytest.mark.unit
    def test_external_service_error(self):
        """Should create external service error."""
        error = ExternalServiceError(
            service="gemini",
            status_code=503,
            message="Service unavailable",
        )

        assert "gemini" in str(error)
        assert "503" in str(error)
        assert error.error_code == "EXTERNAL_SERVICE_ERROR"


class TestExceptionHandling:
    """Test exception handling utilities."""

    @pytest.mark.unit
    def test_handle_prena_exception(self):
        """Should handle PrenaError correctly."""
        error = ToolExecutionError("tool", "action", "Failed")
        result = handle_exception(error, context="testing")

        assert result["error_code"] == "TOOL_EXECUTION_ERROR"
        assert result["context"] == "testing"

    @pytest.mark.unit
    def test_handle_standard_exception(self):
        """Should handle standard Python exceptions."""
        error = ValueError("Something went wrong")
        result = handle_exception(error)

        assert result["error"] == "ValueError"
        assert "Something went wrong" in result["message"]

    @pytest.mark.unit
    def test_handle_exception_with_tool_name(self):
        """Should include tool name in handled exception."""
        error = RuntimeError("Tool failed")
        result = handle_exception(error, tool_name="browser_tool")

        assert result["tool"] == "browser_tool"


class TestErrorHandlingDecorators:
    """Test error handling decorators."""

    @pytest.mark.unit
    def test_with_error_handling_success(self):
        """Decorator should pass through successful results."""
        @with_error_handling(fallback_return="FALLBACK")
        def success_func():
            return "SUCCESS"

        result = success_func()
        assert result == "SUCCESS"

    @pytest.mark.unit
    def test_with_error_handling_exception(self):
        """Decorator should catch exceptions and return fallback."""
        @with_error_handling(fallback_return="FALLBACK")
        def failing_func():
            raise ValueError("Test error")

        result = failing_func()
        assert result == "FALLBACK"

    @pytest.mark.unit
    def test_with_error_handling_none_fallback(self):
        """Decorator should return None on exception if specified."""
        @with_error_handling(fallback_return=None)
        def failing_func():
            raise RuntimeError("Error")

        result = failing_func()
        assert result is None

    @pytest.mark.unit
    def test_catch_and_log_success(self):
        """Decorator should pass through successful results."""
        @catch_and_log()
        def success_func():
            return "SUCCESS"

        result = success_func()
        assert result == "SUCCESS"

    @pytest.mark.unit
    def test_catch_and_log_exception_reraise(self):
        """Decorator should reraise exception when reraise=True."""
        @catch_and_log(reraise=True)
        def failing_func():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            failing_func()

    @pytest.mark.unit
    def test_catch_and_log_context(self):
        """Decorator should include context in log."""
        @catch_and_log(context="processing command")
        def failing_func():
            raise RuntimeError("Failed")

        with pytest.raises(RuntimeError):
            failing_func()


class TestRetryStrategy:
    """Test retry strategy."""

    @pytest.mark.unit
    def test_retry_strategy_initialization(self):
        """Should initialize with max retries."""
        strategy = RetryStrategy(max_retries=5)
        assert strategy.max_retries == 5
        assert strategy.attempt == 0

    @pytest.mark.unit
    def test_retry_strategy_can_recover_initial(self):
        """Should allow recovery initially."""
        strategy = RetryStrategy(max_retries=3)
        error = ValueError("Test")

        assert strategy.can_recover(error) is True

    @pytest.mark.unit
    def test_retry_strategy_can_recover_after_max(self):
        """Should not recover after max attempts."""
        strategy = RetryStrategy(max_retries=2)
        strategy.attempt = 2

        error = ValueError("Test")
        assert strategy.can_recover(error) is False

    @pytest.mark.unit
    def test_retry_strategy_recover_increments(self):
        """Recover should increment attempt counter."""
        strategy = RetryStrategy(max_retries=3, backoff_factor=0)
        error = ValueError("Test")

        initial = strategy.attempt
        strategy.recover(error)
        assert strategy.attempt == initial + 1

    @pytest.mark.unit
    def test_with_recovery_decorator_success(self):
        """Should pass through successful results."""
        strategy = RetryStrategy(max_retries=3)

        @with_recovery(strategy)
        def success_func():
            return "SUCCESS"

        result = success_func()
        assert result == "SUCCESS"

    @pytest.mark.unit
    def test_with_recovery_decorator_retries(self):
        """Should retry on exception until success."""
        strategy = RetryStrategy(max_retries=3, backoff_factor=0)
        call_count = [0]

        @with_recovery(strategy)
        def retry_func():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("Not yet")
            return "SUCCESS"

        result = retry_func()
        assert result == "SUCCESS"
        assert call_count[0] == 3

    @pytest.mark.unit
    def test_with_recovery_decorator_max_retries_exceeded(self):
        """Should raise after max retries exceeded."""
        strategy = RetryStrategy(max_retries=2, backoff_factor=0)

        @with_recovery(strategy)
        def always_fails():
            raise ValueError("Always fails")

        with pytest.raises(ValueError):
            always_fails()


class TestErrorRecoveryIntegration:
    """Integration tests for error handling."""

    @pytest.mark.unit
    def test_full_error_lifecycle(self):
        """Should handle error from creation to recovery."""
        # Create error
        original_error = ToolExecutionError(
            tool_name="test_tool",
            action="test_action",
            message="Failed"
        )

        # Handle error
        handled = handle_exception(original_error, context="integration test")

        assert handled["error_code"] == "TOOL_EXECUTION_ERROR"
        assert handled["context"] == "integration test"

    @pytest.mark.unit
    def test_nested_decorators(self):
        """Should handle nested error handling decorators."""
        retry_strategy = RetryStrategy(max_retries=2, backoff_factor=0)

        @with_error_handling(fallback_return="FALLBACK")
        @with_recovery(retry_strategy)
        def complex_func():
            raise ValueError("Error")

        result = complex_func()
        assert result == "FALLBACK"

    @pytest.mark.unit
    def test_exception_preservation_through_handlers(self):
        """Should preserve exception details through handlers."""
        original_error = ValidationError(
            field="email",
            reason="Invalid format",
            extra_info="user@invalid"
        )

        handled = handle_exception(original_error)

        assert handled["error_code"] == "VALIDATION_ERROR"
        assert "email" in handled["details"]["field"] or "email" in str(handled)
