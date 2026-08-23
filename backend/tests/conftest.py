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