# -*- coding: utf-8 -*-
"""
pytest conftest
================
The real project only ever runs on Windows (pyautogui, pywin32, Windows
Camera/WhatsApp Desktop automation, etc.), but the PURE LOGIC this suite
targets — title parsing, path-search fallback, fuzzy app-name matching,
the goal_loop control flow, session updaters, cooldown/retry logic, text
naturalization — has nothing to do with any of that. Rather than skip the
whole suite outside Windows, we stub the handful of hardware/UI-automation
modules that get imported at module level (not lazily inside functions) so
`import tools` / `import whatsapp_actions` / `import app.dependencies`
succeeds anywhere, and the tests below can exercise the actual functions
instead of a re-implementation of their logic.

This is intentionally a thin stub layer, not a mock framework: enough for
imports to succeed and for tests that don't call the stubbed functions to
run normally. Tests that DO need specific stubbed behavior (e.g. a
particular win32gui.GetWindowText return value, or a Gemini API response)
patch the stub further themselves via monkeypatch/unittest.mock — see
individual test files.

v1.1.1 addition: google.genai, edge_tts, and selenium are real project
dependencies (see requirements.txt) and are NOT stubbed if actually
installed — tests for dependencies.py / speech_naturalizer.py / tts.py /
chrome_session.py should exercise the real SDK's shape by mocking specific
methods (Client, Communicate, webdriver.Chrome), not a fake module. They
are only stubbed here as a fallback so the pure-logic parts of the suite
still run on a lighter dev machine that hasn't installed the full
Windows-automation dependency set.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

# So `import tools`, `import agent.goal_loop`, etc. work no matter what
# directory `pytest` is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _stub_module(name: str, **attrs) -> None:
    if name in sys.modules:
        return
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod


def _stub_if_missing(name: str, **attrs) -> None:
    """Only stub if the REAL package isn't actually importable — on the
    real Windows dev/CI machine (requirements.txt installed), the genuine
    SDK is used; only a lighter environment falls back to the stub."""
    try:
        __import__(name)
        return
    except ImportError:
        _stub_module(name, **attrs)


_stub_module(
    "pyautogui",
    FAILSAFE=True,
    PAUSE=0,
    size=lambda: (1920, 1080),
    click=lambda *a, **k: None,
    press=lambda *a, **k: None,
    hotkey=lambda *a, **k: None,
    screenshot=lambda *a, **k: None,
    locateOnScreen=lambda *a, **k: None,
    center=lambda loc: loc,
)
_stub_module("pyperclip", copy=lambda *a, **k: None, paste=lambda: "")
_stub_module(
    "win32gui",
    GetForegroundWindow=lambda: 0,
    GetWindowText=lambda hwnd: "",
    GetWindowRect=lambda hwnd: (0, 0, 1920, 1080),
    IsWindowVisible=lambda hwnd: True,
    EnumWindows=lambda callback, extra: None,
    PostMessage=lambda *a, **k: None,
)
_stub_module("win32con", WM_CLOSE=0x0010)
_stub_module("win32process", GetWindowThreadProcessId=lambda hwnd: (0, 0))

# ── v1.1.1: fallback stubs for real (but possibly-not-installed-here) deps ──

if "google" not in sys.modules:
    _stub_if_missing("google")
    google_mod = sys.modules.get("google") or _stub_module("google") or sys.modules["google"]

try:
    import google.genai  # noqa: F401
except ImportError:
    google_pkg = sys.modules.get("google") or types.ModuleType("google")
    google_pkg.__path__ = []  # mark as a package so submodule imports resolve
    sys.modules["google"] = google_pkg

    genai_mod = types.ModuleType("google.genai")

    class _StubClient:  # pragma: no cover - replaced by tests via mock.patch
        def __init__(self, api_key=None):
            self.api_key = api_key

    genai_mod.Client = _StubClient
    sys.modules["google.genai"] = genai_mod
    google_pkg.genai = genai_mod

    genai_types_mod = types.ModuleType("google.genai.types")

    class _StubGenerateContentConfig:  # pragma: no cover
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    genai_types_mod.GenerateContentConfig = _StubGenerateContentConfig
    sys.modules["google.genai.types"] = genai_types_mod
    genai_mod.types = genai_types_mod

try:
    import edge_tts  # noqa: F401
except ImportError:
    edge_tts_mod = types.ModuleType("edge_tts")

    class _StubCommunicate:  # pragma: no cover - replaced by tests via mock.patch
        def __init__(self, **kwargs):
            self._kwargs = kwargs

        async def save(self, filename):
            with open(filename, "wb") as f:
                f.write(b"")

    edge_tts_mod.Communicate = _StubCommunicate
    sys.modules["edge_tts"] = edge_tts_mod

try:
    import selenium  # noqa: F401
    import selenium.webdriver  # noqa: F401
    import selenium.webdriver.chrome.options  # noqa: F401
    import selenium.webdriver.edge.options  # noqa: F401
except ImportError:
    selenium_mod = types.ModuleType("selenium")
    selenium_mod.__path__ = []
    sys.modules["selenium"] = selenium_mod

    webdriver_mod = types.ModuleType("selenium.webdriver")
    webdriver_mod.__path__ = []

    class _StubDriver:  # pragma: no cover - replaced by tests via mock.patch
        def __init__(self, options=None):
            self.options = options
            self._handles = ["stub-window"]

        @property
        def window_handles(self):
            return self._handles

    webdriver_mod.Chrome = _StubDriver
    webdriver_mod.Edge = _StubDriver
    sys.modules["selenium.webdriver"] = webdriver_mod
    selenium_mod.webdriver = webdriver_mod

    chrome_pkg = types.ModuleType("selenium.webdriver.chrome")
    chrome_pkg.__path__ = []
    sys.modules["selenium.webdriver.chrome"] = chrome_pkg
    chrome_options_mod = types.ModuleType("selenium.webdriver.chrome.options")

    class _StubOptions:  # pragma: no cover
        def __init__(self):
            self.debugger_address = None

    chrome_options_mod.Options = _StubOptions
    sys.modules["selenium.webdriver.chrome.options"] = chrome_options_mod

    edge_pkg = types.ModuleType("selenium.webdriver.edge")
    edge_pkg.__path__ = []
    sys.modules["selenium.webdriver.edge"] = edge_pkg
    edge_options_mod = types.ModuleType("selenium.webdriver.edge.options")
    edge_options_mod.Options = _StubOptions
    sys.modules["selenium.webdriver.edge.options"] = edge_options_mod


# ── v1.1.1: Additional Fixtures for Enhanced Testing ─────────────────────────

import pytest
import json
import tempfile
from pathlib import Path
from typing import Generator, Any, Dict
from unittest.mock import MagicMock, patch, AsyncMock


@pytest.fixture(autouse=True)
def setup_test_env():
    """Set up test environment variables before each test."""
    import os
    os.environ["PRERNA_ENV"] = "test"
    os.environ["GEMINI_API_KEY"] = "test-key-xyz"
    os.environ["LOG_LEVEL"] = "DEBUG"
    yield
    # Cleanup
    for key in ["PRERNA_ENV", "GEMINI_API_KEY", "LOG_LEVEL"]:
        if key in os.environ:
            del os.environ[key]


@pytest.fixture
def temp_memory_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for memory storage during tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_tool_result():
    """Provide sample ToolResult instances for testing."""
    from agent.registry import ToolResult
    return {
        "success": ToolResult(True, "Operation successful"),
        "failure": ToolResult(False, "Operation failed"),
        "with_speech": ToolResult(True, "Long message here", speech="Short response"),
        "with_data": ToolResult(True, "ok", data={"key": "value"}),
    }


@pytest.fixture
def mock_memory_manager():
    """Mock memory manager for tool testing."""
    with patch("memory.memory_manager.MemoryManager") as mock_mem:
        instance = MagicMock()
        instance.add_conversation_turn = MagicMock()
        instance.get_recent_context = MagicMock(return_value="")
        instance.save_memory = MagicMock()
        instance.load_memory = MagicMock(return_value={})
        mock_mem.return_value = instance
        yield instance


@pytest.fixture
def sample_chat_request() -> Dict[str, Any]:
    """Sample chat request for API testing."""
    return {
        "message": "What's the weather?",
        "session_id": "test-session-123",
        "context": {
            "user_location": "New York",
        }
    }


@pytest.fixture
def sample_chat_response() -> Dict[str, Any]:
    """Sample expected chat response structure."""
    return {
        "response": "The weather is sunny today.",
        "session_id": "test-session-123",
        "success": True,
        "steps": [
            {
                "tool": "search_tool",
                "action": "search",
                "status": "completed",
            }
        ],
    }


class AssertionHelpers:
    """Collection of assertion helpers for Prerna tests."""

    @staticmethod
    def assert_tool_result_valid(result: Any) -> None:
        """Assert that a ToolResult has valid structure."""
        from agent.registry import ToolResult
        assert isinstance(result, ToolResult), f"Expected ToolResult, got {type(result)}"
        assert isinstance(result.success, bool), "success must be bool"
        assert isinstance(result.message, str), "message must be str"
        if result.speech is not None:
            assert isinstance(result.speech, str), "speech must be str or None"

    @staticmethod
    def assert_api_response_valid(response: dict) -> None:
        """Assert that an API response has valid structure."""
        assert "response" in response, "Missing 'response' field"
        assert "success" in response, "Missing 'success' field"
        assert isinstance(response["success"], bool), "success must be bool"

    @staticmethod
    def assert_plan_valid(plan: list) -> None:
        """Assert that an execution plan is valid."""
        assert isinstance(plan, list), "Plan must be a list"
        for step in plan:
            assert "tool" in step, "Step missing 'tool' field"
            assert "action" in step, "Step missing 'action' field"


@pytest.fixture
def helpers() -> AssertionHelpers:
    """Provide assertion helpers."""
    return AssertionHelpers()


def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers", "unit: Mark test as a unit test (fast, isolated)"
    )
    config.addinivalue_line(
        "markers", "integration: Mark test as integration test (slower)"
    )
    config.addinivalue_line(
        "markers", "slow: Mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "dangerous: Mark test as potentially destructive"
    )