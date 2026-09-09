"""
type_hints.py
=============
Common type aliases and protocols for Prerna codebase.

This module centralizes type definitions to improve:
  - Static type checking (mypy)
  - IDE autocompletion
  - Documentation clarity
  - Runtime validation

v1.1.1 addition: Comprehensive type system
"""

from __future__ import annotations

from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Union,
    TypeVar,
    Generic,
)
from dataclasses import dataclass

# ── Common Type Aliases ────────────────────────────────────────────────────────

# JSON-serializable types
JSON = Union[str, int, float, bool, None, Dict[str, Any], List[Any]]

# Arguments passed to tool actions
ToolArgs = Dict[str, Any]

# Execution context shared across tools
ExecutionContext = Dict[str, Any]

# Plan step definition
PlanStep = Dict[str, Any]

# Multiple steps
ExecutionPlan = List[PlanStep]

# API request/response payloads
APIPayload = Dict[str, Any]

# Long-term storage (facts, user preferences, etc.)
MemoryStore = Dict[str, Any]

# Session/conversation state
SessionState = Dict[str, Any]

# Filter predicates
FilterPredicate = Callable[[Any], bool]

T = TypeVar("T")


# ── Protocol Definitions ───────────────────────────────────────────────────────

class Serializable(Protocol):
    """Protocol for objects that can be serialized to JSON."""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        ...

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Serializable:
        """Create from dictionary."""
        ...


class ToolActionHandler(Protocol):
    """Protocol for tool action handler functions."""

    def __call__(self, **kwargs: Any) -> Any:
        """Execute tool action with keyword arguments."""
        ...


class EventHandler(Protocol):
    """Protocol for event handler functions."""

    def __call__(self, event: Any) -> None:
        """Handle an event."""
        ...


class LoggerLike(Protocol):
    """Protocol for objects compatible with standard logging.Logger."""

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log debug message."""
        ...

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log info message."""
        ...

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log warning message."""
        ...

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log error message."""
        ...

    def critical(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log critical message."""
        ...


# ── Generic Base Classes ───────────────────────────────────────────────────────

@dataclass
class Result(Generic[T]):
    """Generic result type for operations that can succeed or fail."""

    success: bool
    value: Optional[T] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Validate result state."""
        if self.success and self.error is not None:
            raise ValueError("Success=True but error is set")
        if not self.success and self.value is not None:
            raise ValueError("Success=False but value is set")


@dataclass
class PagedResult(Generic[T]):
    """Result with pagination support."""

    items: List[T]
    total_count: int
    page: int
    page_size: int
    has_next: bool = False

    @property
    def total_pages(self) -> int:
        """Calculate total number of pages."""
        return (self.total_count + self.page_size - 1) // self.page_size


# ── Validation Helpers ────────────────────────────────────────────────────────

def is_valid_json(obj: Any) -> bool:
    """Check if object is JSON-serializable."""
    try:
        import json
        json.dumps(obj)
        return True
    except (TypeError, ValueError):
        return False


def assert_type(value: Any, expected_type: type, name: str = "value") -> None:
    """Assert that value is of expected type.

    Args:
        value: Value to check
        expected_type: Expected type
        name: Parameter name for error messages

    Raises:
        TypeError: If value is not of expected type
    """
    if not isinstance(value, expected_type):
        raise TypeError(
            f"{name} must be {expected_type.__name__}, "
            f"got {type(value).__name__}: {value!r}"
        )


def assert_not_empty(value: str, name: str = "value") -> None:
    """Assert that string is not empty.

    Args:
        value: String to check
        name: Parameter name for error messages

    Raises:
        ValueError: If value is empty
    """
    if not value or not value.strip():
        raise ValueError(f"{name} cannot be empty")


def assert_in_range(
    value: Union[int, float],
    min_val: Union[int, float],
    max_val: Union[int, float],
    name: str = "value",
) -> None:
    """Assert that numeric value is in range.

    Args:
        value: Value to check
        min_val: Minimum value (inclusive)
        max_val: Maximum value (inclusive)
        name: Parameter name for error messages

    Raises:
        ValueError: If value is out of range
    """
    if not (min_val <= value <= max_val):
        raise ValueError(
            f"{name} must be between {min_val} and {max_val}, got {value}"
        )


def get_or_raise(
    mapping: Dict[str, T],
    key: str,
    error_message: Optional[str] = None,
) -> T:
    """Get value from dict or raise KeyError with custom message.

    Args:
        mapping: Dictionary to get from
        key: Key to look up
        error_message: Custom error message (if None, uses default)

    Returns:
        Value from dictionary

    Raises:
        KeyError: If key not found
    """
    if key not in mapping:
        if error_message is None:
            error_message = f"Key '{key}' not found"
        raise KeyError(error_message)
    return mapping[key]


# ── Common Enumerations ────────────────────────────────────────────────────────

class StatusCode(int):
    """HTTP-like status codes for operations."""

    OK = 200
    CREATED = 201
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    ERROR = 500
    SERVICE_UNAVAILABLE = 503


class LogLevel(str):
    """Log level names."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
