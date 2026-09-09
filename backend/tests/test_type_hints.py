"""
test_type_hints.py
==================
Tests for utils/type_hints.py

Tests type validation, assertion helpers, and generic types.

v1.1.1 addition: Type system validation tests
"""

from __future__ import annotations

import pytest
from utils.type_hints import (
    JSON,
    Result,
    PagedResult,
    is_valid_json,
    assert_type,
    assert_not_empty,
    assert_in_range,
    get_or_raise,
    StatusCode,
    LogLevel,
)


class TestTypeAliases:
    """Test type alias definitions."""

    @pytest.mark.unit
    def test_json_type_string(self):
        """JSON type should accept strings."""
        value: JSON = "hello"
        assert isinstance(value, str)

    @pytest.mark.unit
    def test_json_type_number(self):
        """JSON type should accept numbers."""
        int_val: JSON = 42
        float_val: JSON = 3.14
        assert isinstance(int_val, int)
        assert isinstance(float_val, float)

    @pytest.mark.unit
    def test_json_type_bool(self):
        """JSON type should accept booleans."""
        value: JSON = True
        assert isinstance(value, bool)

    @pytest.mark.unit
    def test_json_type_dict(self):
        """JSON type should accept dictionaries."""
        value: JSON = {"key": "value"}
        assert isinstance(value, dict)

    @pytest.mark.unit
    def test_json_type_list(self):
        """JSON type should accept lists."""
        value: JSON = [1, 2, 3]
        assert isinstance(value, list)

    @pytest.mark.unit
    def test_json_type_none(self):
        """JSON type should accept None."""
        value: JSON = None
        assert value is None


class TestResultType:
    """Test generic Result type."""

    @pytest.mark.unit
    def test_result_success(self):
        """Should create successful result."""
        result = Result[str](success=True, value="Success!")
        assert result.success is True
        assert result.value == "Success!"
        assert result.error is None

    @pytest.mark.unit
    def test_result_failure(self):
        """Should create failed result."""
        result = Result[str](success=False, error="Something failed")
        assert result.success is False
        assert result.error == "Something failed"
        assert result.value is None

    @pytest.mark.unit
    def test_result_with_metadata(self):
        """Should attach metadata to result."""
        result = Result[int](
            success=True,
            value=42,
            metadata={"duration_ms": 1234}
        )
        assert result.metadata["duration_ms"] == 1234

    @pytest.mark.unit
    def test_result_success_with_error_raises(self):
        """Should raise if success=True but error is set."""
        with pytest.raises(ValueError):
            Result[str](success=True, value="OK", error="Has error")

    @pytest.mark.unit
    def test_result_failure_with_value_raises(self):
        """Should raise if success=False but value is set."""
        with pytest.raises(ValueError):
            Result[str](success=False, error="Failed", value="Has value")


class TestPagedResultType:
    """Test PagedResult generic type."""

    @pytest.mark.unit
    def test_paged_result_creation(self):
        """Should create paged result with pagination info."""
        items = ["a", "b", "c"]
        result = PagedResult[str](
            items=items,
            total_count=30,
            page=1,
            page_size=10,
        )
        assert result.items == items
        assert result.total_count == 30
        assert result.page == 1
        assert result.page_size == 10

    @pytest.mark.unit
    def test_paged_result_total_pages_calculation(self):
        """Should calculate total pages correctly."""
        result = PagedResult[int](
            items=[1, 2, 3],
            total_count=25,
            page=1,
            page_size=10,
        )
        assert result.total_pages == 3

    @pytest.mark.unit
    def test_paged_result_has_next(self):
        """Should indicate if more pages exist."""
        result = PagedResult[str](
            items=["a", "b"],
            total_count=20,
            page=1,
            page_size=10,
            has_next=True,
        )
        assert result.has_next is True

    @pytest.mark.unit
    def test_paged_result_total_pages_rounding(self):
        """Should round up total pages calculation."""
        result = PagedResult[int](
            items=[],
            total_count=23,  # Not evenly divisible by 10
            page=0,
            page_size=10,
        )
        # 23 items in pages of 10 = 3 pages
        assert result.total_pages == 3


class TestValidationFunctions:
    """Test validation helper functions."""

    @pytest.mark.unit
    def test_is_valid_json_dict(self):
        """Should validate JSON-serializable dict."""
        assert is_valid_json({"key": "value"}) is True

    @pytest.mark.unit
    def test_is_valid_json_list(self):
        """Should validate JSON-serializable list."""
        assert is_valid_json([1, 2, 3, "four"]) is True

    @pytest.mark.unit
    def test_is_valid_json_primitives(self):
        """Should validate JSON-serializable primitives."""
        assert is_valid_json("string") is True
        assert is_valid_json(42) is True
        assert is_valid_json(3.14) is True
        assert is_valid_json(True) is True
        assert is_valid_json(None) is True

    @pytest.mark.unit
    def test_is_valid_json_invalid_object(self):
        """Should reject non-JSON-serializable objects."""
        class CustomClass:
            pass

        assert is_valid_json(CustomClass()) is False

    @pytest.mark.unit
    def test_is_valid_json_complex_nested(self):
        """Should validate complex nested structures."""
        data = {
            "users": [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"},
            ],
            "count": 2,
        }
        assert is_valid_json(data) is True

    @pytest.mark.unit
    def test_assert_type_success(self):
        """Should not raise for correct type."""
        assert_type("hello", str, "message")
        assert_type(42, int, "count")
        assert_type([1, 2], list, "items")

    @pytest.mark.unit
    def test_assert_type_failure(self):
        """Should raise TypeError for wrong type."""
        with pytest.raises(TypeError, match="must be str"):
            assert_type(42, str, "value")

    @pytest.mark.unit
    def test_assert_not_empty_success(self):
        """Should not raise for non-empty string."""
        assert_not_empty("hello", "name")
        assert_not_empty("   not empty", "value")

    @pytest.mark.unit
    def test_assert_not_empty_failure_empty_string(self):
        """Should raise for empty string."""
        with pytest.raises(ValueError, match="cannot be empty"):
            assert_not_empty("", "name")

    @pytest.mark.unit
    def test_assert_not_empty_failure_whitespace(self):
        """Should raise for whitespace-only string."""
        with pytest.raises(ValueError):
            assert_not_empty("   ", "value")

    @pytest.mark.unit
    def test_assert_in_range_success(self):
        """Should not raise for value in range."""
        assert_in_range(5, 0, 10, "value")
        assert_in_range(0, 0, 10, "value")
        assert_in_range(10, 0, 10, "value")

    @pytest.mark.unit
    def test_assert_in_range_failure_too_low(self):
        """Should raise for value below range."""
        with pytest.raises(ValueError, match="between"):
            assert_in_range(-1, 0, 10, "value")

    @pytest.mark.unit
    def test_assert_in_range_failure_too_high(self):
        """Should raise for value above range."""
        with pytest.raises(ValueError, match="between"):
            assert_in_range(11, 0, 10, "value")

    @pytest.mark.unit
    def test_assert_in_range_float_values(self):
        """Should work with float values."""
        assert_in_range(0.5, 0.0, 1.0, "confidence")
        assert_in_range(99.9, 0.0, 100.0, "percentage")

    @pytest.mark.unit
    def test_get_or_raise_success(self):
        """Should return value from dict."""
        data = {"name": "Alice", "age": 30}
        assert get_or_raise(data, "name") == "Alice"

    @pytest.mark.unit
    def test_get_or_raise_failure_default_message(self):
        """Should raise KeyError with default message."""
        data = {"name": "Alice"}
        with pytest.raises(KeyError, match="Key 'age' not found"):
            get_or_raise(data, "age")

    @pytest.mark.unit
    def test_get_or_raise_failure_custom_message(self):
        """Should raise KeyError with custom message."""
        data = {}
        custom_msg = "Age is required"
        with pytest.raises(KeyError, match=custom_msg):
            get_or_raise(data, "age", error_message=custom_msg)


class TestEnumerations:
    """Test enumeration constants."""

    @pytest.mark.unit
    def test_status_code_values(self):
        """Should have correct HTTP status codes."""
        assert StatusCode.OK == 200
        assert StatusCode.CREATED == 201
        assert StatusCode.BAD_REQUEST == 400
        assert StatusCode.NOT_FOUND == 404
        assert StatusCode.ERROR == 500

    @pytest.mark.unit
    def test_log_level_values(self):
        """Should have correct log level names."""
        assert LogLevel.DEBUG == "DEBUG"
        assert LogLevel.INFO == "INFO"
        assert LogLevel.WARNING == "WARNING"
        assert LogLevel.ERROR == "ERROR"
        assert LogLevel.CRITICAL == "CRITICAL"

    @pytest.mark.unit
    def test_log_level_string_comparison(self):
        """Should work with string comparisons."""
        level = LogLevel.INFO
        assert level == "INFO"
        assert level.upper() == "INFO"
