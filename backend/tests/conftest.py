# -*- coding: utf-8 -*-
"""
pytest conftest
================
The real project only ever runs on Windows (pyautogui, pywin32, Windows
Camera/WhatsApp Desktop automation, etc.), but the PURE LOGIC this suite
targets — title parsing, path-search fallback, fuzzy app-name matching,
the goal_loop control flow, session updaters — has nothing to do with any
of that. Rather than skip the whole suite outside Windows, we stub the
handful of hardware/UI-automation modules that get imported at module
level (not lazily inside functions) so `import tools` / `import
whatsapp_actions` succeeds anywhere, and the tests below can exercise the
actual functions instead of a re-implementation of their logic.

This is intentionally a thin stub layer, not a mock framework: enough for
imports to succeed and for tests that don't call the stubbed functions to
run normally. Tests that DO need specific stubbed behavior (e.g. a
particular win32gui.GetWindowText return value) patch the stub further
themselves via monkeypatch/unittest.mock — see individual test files.
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
