"""
Tests for v1.2.1 Bug 2: system_tool.py's new close_app action.

The core thing these tests must prove is the safety guarantee: Prerna's own
windows can never be closed by a general "close X" command, and that
guarantee is structural (own PID excluded at enumeration time), not just a
name-matching heuristic that could be defeated by an unlucky title/app-name
collision.
"""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tools import system_tool  # noqa: E402


def _win(hwnd, title, process_name, pid):
    return {"hwnd": hwnd, "title": title, "process_name": process_name, "pid": pid}


class TestSelfCloseRefusal:
    @pytest.mark.parametrize("name", ["prerna", "Prerna", "yourself", "this app", "this program"])
    def test_refuses_self_close_names_without_even_enumerating(self, name):
        with patch.object(system_tool, "_enum_visible_windows") as mock_enum:
            result = system_tool.close_app(name)
        assert not result.success
        mock_enum.assert_not_called()  # refused before ever looking at windows


class TestEnumerationExcludesOwnProcess:
    def test_own_pid_windows_never_returned(self, monkeypatch):
        # Simulate a window that belongs to our own process turning up in
        # EnumWindows — it must never make it into the returned list, no
        # matter what its title says.
        own_pid = os.getpid()

        class FakeWin32Gui:
            @staticmethod
            def IsWindowVisible(hwnd):
                return True

            @staticmethod
            def GetWindowText(hwnd):
                return "Prerna Console - Chrome"  # deliberately name-colliding title

            @staticmethod
            def EnumWindows(callback, extra):
                callback(12345, extra)

        class FakeWin32Process:
            @staticmethod
            def GetWindowThreadProcessId(hwnd):
                return (0, own_pid)

        with patch.dict(sys.modules, {"win32gui": FakeWin32Gui, "win32process": FakeWin32Process}), \
             patch.dict(sys.modules, {"psutil": __import__("types").SimpleNamespace(
                 Process=lambda pid: __import__("types").SimpleNamespace(name=lambda: "python.exe")
             )}):
            result = system_tool._enum_visible_windows()

        assert result == []


class TestCloseAppMatching:
    def test_no_windows_available_fails_cleanly(self):
        with patch.object(system_tool, "_enum_visible_windows", return_value=[]):
            result = system_tool.close_app("chrome")
        assert not result.success

    def test_matches_by_process_hint(self):
        windows = [_win(1, "Inbox - Gmail - Google Chrome", "chrome.exe", 111)]
        with patch.object(system_tool, "_enum_visible_windows", return_value=windows), \
             patch.dict(sys.modules, {
                 "win32gui": __import__("types").SimpleNamespace(PostMessage=lambda *a: None),
                 "win32con": __import__("types").SimpleNamespace(WM_CLOSE=0x0010),
             }):
            result = system_tool.close_app("chrome")
        assert result.success
        assert "Inbox - Gmail - Google Chrome" in result.message

    def test_matches_explorer_by_title_never_by_bare_process_kill(self):
        # Explorer windows are matched (and closed) individually by title;
        # this test just confirms the match works via title, not that the
        # whole explorer.exe process gets touched (there's no taskkill path
        # in this implementation at all — WM_CLOSE only, per-window).
        windows = [_win(2, "Downloads", "explorer.exe", 222)]
        with patch.object(system_tool, "_enum_visible_windows", return_value=windows), \
             patch.dict(sys.modules, {
                 "win32gui": __import__("types").SimpleNamespace(PostMessage=lambda *a: None),
                 "win32con": __import__("types").SimpleNamespace(WM_CLOSE=0x0010),
             }):
            result = system_tool.close_app("downloads")
        assert result.success

    def test_no_match_fails_cleanly(self):
        windows = [_win(3, "Unrelated Window", "unrelated.exe", 333)]
        with patch.object(system_tool, "_enum_visible_windows", return_value=windows):
            result = system_tool.close_app("chrome")
        assert not result.success

    def test_multiple_matches_all_closed(self):
        windows = [
            _win(4, "Tab A - Google Chrome", "chrome.exe", 444),
            _win(5, "Tab B - Google Chrome", "chrome.exe", 444),
        ]
        calls = []
        with patch.object(system_tool, "_enum_visible_windows", return_value=windows), \
             patch.dict(sys.modules, {
                 "win32gui": __import__("types").SimpleNamespace(
                     PostMessage=lambda hwnd, *a: calls.append(hwnd)
                 ),
                 "win32con": __import__("types").SimpleNamespace(WM_CLOSE=0x0010),
             }):
            result = system_tool.close_app("chrome")
        assert result.success
        assert len(calls) == 2


class TestMatchesAppHelper:
    def test_hint_match_on_process_name(self):
        w = _win(1, "some title", "chrome.exe", 1)
        assert system_tool._matches_app(w, "chrome", ["chrome.exe"])

    def test_title_fallback_when_no_hints_defined(self):
        w = _win(1, "Downloads", "explorer.exe", 1)
        assert system_tool._matches_app(w, "downloads", [])

    def test_no_match_when_neither_hint_nor_title_match(self):
        w = _win(1, "Unrelated", "unrelated.exe", 1)
        assert not system_tool._matches_app(w, "chrome", ["chrome.exe"])