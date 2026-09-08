"""
error_handler.py
================
Centralized error handling and exception types for Prerna.

Provides:
  - Custom exception types organized by domain
  - Graceful error conversion to ToolResult
  - Error context preservation
  - Structured error logging

v1.1.1 addition: Comprehensive error handling system
"""

from __future__ import annotations

from typing import Optional, Type, Any, Dict, Callable
from functools import wraps
from utils.logger import get_logger

logger = get_logger(__name__)


# ── Custom Exception Types ────────────────────────────────────────────────────

class PrenaError(Exception):
    """Base exception for all Prerna errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "PRERNA_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ):
        """Initialize Prerna error.

        Args:
            message: Human-readable error message
            error_code: Machine-readable error code
            details: Additional context about the error
        """
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}
        self.message = message

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for serialization."""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "error_code": self.error_code,
            "details": self.details,
        }


class ToolExecutionError(PrenaError):
    """Error during tool execution."""

    def __init__(self, tool_name: str, action: str, message: str, **details):
        super().__init__(
            message=f"Tool '{tool_name}' action '{action}' failed: {message}",
            error_code="TOOL_EXECUTION_ERROR",
            details={"tool": tool_name, "action": action, **details},
        )


class ValidationError(PrenaError):
    """Validation of inputs/arguments failed."""

    def __init__(self, field: str, reason: str, **details):
        super().__init__(
            message=f"Validation failed for field '{field}': {reason}",
            error_code="VALIDATION_ERROR",
            details={"field": field, **details},
        )


class ConfigurationError(PrenaError):
    """Configuration is invalid or missing."""

    def __init__(self, setting: str, reason: str, **details):
        super().__init__(
            message=f"Configuration error for '{setting}': {reason}",
            error_code="CONFIG_ERROR",
            details={"setting": setting, **details},
        )


class PermissionError(PrenaError):
    """Operation requires user confirmation/permission."""

    def __init__(self, operation: str, reason: str = "", **details):
        super().__init__(
            message=f"Permission required for: {operation}" + (f" ({reason})" if reason else ""),
            error_code="PERMISSION_REQUIRED",
            details={"operation": operation, **details},
        )


class RateLimitError(PrenaError):
    """Rate limit exceeded."""

    def __init__(self, service: str, retry_after: Optional[int] = None, **details):
        super().__init__(
            message=f"Rate limit exceeded for {service}" + (
                f", retry after {retry_after}s" if retry_after else ""
            ),
            error_code="RATE_LIMIT_EXCEEDED",
            details={"service": service, "retry_after": retry_after, **details},
        )


class TimeoutError(PrenaError):
    """Operation timed out."""

    def __init__(self, operation: str, timeout_seconds: float, **details):
        super().__init__(
            message=f"Operation '{operation}' timed out after {timeout_seconds}s",
            error_code="TIMEOUT",
            details={"operation": operation, "timeout_seconds": timeout_seconds, **details},
        )


class ResourceNotFoundError(PrenaError):
    """Requested resource not found."""

    def __init__(self, resource_type: str, resource_id: str, **details):
        super().__init__(
            message=f"{resource_type} not found: {resource_id}",
            error_code="NOT_FOUND",
            details={"resource_type": resource_type, "resource_id": resource_id, **details},
        )


class ExternalServiceError(PrenaError):
    """Error from external service (API, browser, etc.)."""

    def __init__(self, service: str, status_code: Optional[int] = None, message: str = "", **details):
        super().__init__(
            message=f"External service '{service}' error" + (f" (HTTP {status_code})" if status_code else "") + (
                f": {message}" if message else ""
            ),
            error_code="EXTERNAL_SERVICE_ERROR",
            details={"service": service, "status_code": status_code, **details},
        )


# ── Error Handlers ────────────────────────────────────────────────────────────

def handle_exception(
    exception: Exception,
    context: Optional[str] = None,
    tool_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert exception to structured error dict.

    Args:
        exception: Exception to handle
        context: Optional context description
        tool_name: Optional tool name for logging

    Returns:
        Structured error dictionary
    """
    if isinstance(exception, PrenaError):
        error_dict = exception.to_dict()
    else:
        error_dict = {
            "error": exception.__class__.__name__,
            "message": str(exception),
            "error_code": "UNKNOWN_ERROR",
        }

    if context:
        error_dict["context"] = context
    if tool_name:
        error_dict["tool"] = tool_name

    logger.error(f"Exception handled: {error_dict}")
    return error_dict


def with_error_handling(
    fallback_return: Optional[Any] = None,
    log_level: str = "error",
) -> Callable:
    """Decorator to catch exceptions and convert to ToolResult.

    Args:
        fallback_return: Value to return on exception
        log_level: Logging level for exceptions (error, warning, info, debug)

    Example:
        @with_error_handling(fallback_return=ToolResult(False, "Failed"))
        def my_tool_action(**kwargs):
            return ToolResult(True, "Success")
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Get the logger method directly instead of using logger.log()
                log_method = getattr(logger, log_level.lower(), logger.error)
                log_method(f"Error in {func.__name__}: {e}", exc_info=True)
                return fallback_return

        return wrapper

    return decorator


def catch_and_log(
    reraise: bool = False,
    context: Optional[str] = None,
) -> Callable:
    """Decorator to log exceptions without catching them.

    Args:
        reraise: Whether to reraise exception after logging
        context: Context description for logging

    Example:
        @catch_and_log(context="processing user command")
        def process_command(cmd):
            return execute(cmd)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(
                    f"Exception in {func.__name__}" + (f" ({context})" if context else "") + f": {e}",
                    exc_info=True,
                )
                if reraise:
                    raise
                raise

        return wrapper

    return decorator


# ── Error Recovery ────────────────────────────────────────────────────────────

class ErrorRecoveryStrategy:
    """Base class for error recovery strategies."""

    def can_recover(self, exception: Exception) -> bool:
        """Check if this strategy can handle the exception."""
        raise NotImplementedError

    def recover(self, exception: Exception) -> Any:
        """Attempt to recover from the exception.

        Returns:
            Recovery result, or raises if recovery not possible
        """
        raise NotImplementedError


class RetryStrategy(ErrorRecoveryStrategy):
    """Retry an operation multiple times."""

    def __init__(self, max_retries: int = 3, backoff_factor: float = 1.0):
        """Initialize retry strategy.

        Args:
            max_retries: Maximum number of retries
            backoff_factor: Multiplier for exponential backoff (0 = no backoff)
        """
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.attempt = 0

    def can_recover(self, exception: Exception) -> bool:
        """Can retry if we haven't exceeded max retries."""
        return self.attempt < self.max_retries

    def recover(self, exception: Exception) -> None:
        """Increment attempt counter and optionally sleep."""
        import time

        self.attempt += 1
        if self.backoff_factor > 0:
            wait_time = self.backoff_factor ** self.attempt
            logger.info(f"Retry {self.attempt}/{self.max_retries}, waiting {wait_time}s")
            time.sleep(wait_time)


def with_recovery(strategy: ErrorRecoveryStrategy) -> Callable:
    """Decorator to apply error recovery strategy.

    Args:
        strategy: Recovery strategy to use

    Example:
        strategy = RetryStrategy(max_retries=3)
        @with_recovery(strategy)
        def flaky_operation():
            return call_external_api()
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if strategy.can_recover(e):
                        strategy.recover(e)
                    else:
                        logger.error(f"Recovery failed for {func.__name__}")
                        raise

        return wrapper

    return decorator
