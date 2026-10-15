"""
Tests for v1.2.1 Bug 3: ChromeSessionManager.bring_to_foreground() and its
_find_main_window_hwnd() helper.

The actual SetForegroundWindow/AttachThreadInput calls can only be verified
for real on a live Windows machine with a real browser window open — these
tests verify the *decision logic* around them: when a window is found vs.
not found, that pywin32-unavailable is handled as "can't do it" rather than
a crash, and that only our own automation processes are ever considered
candidates (never a stray window from an unrelated process).
"""
import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tools import chrome_session  # noqa: E402


@pytest.fixture
def manager():
    m = chrome_session.ChromeSessionManager()
    m._engine = {"name": "chrome", "display_name": "Google Chrome", "process_name": "chrome.exe"}
    return m


class TestBringToForegroundNoEngine:
    def test_returns_false_when_no_engine_resolved(self):
        m = chrome_session.ChromeSessionManager()
        m._engine = None
        assert m.bring_to_foreground() is False


class TestBringToForegroundNoWindowFound:
    def test_returns_false_when_no_matching_window(self, manager):
        with patch.object(chrome_session, "_find_main_window_hwnd", return_value=None):
            assert manager.bring_to_foreground() is False


class TestBringToForegroundHappyPath:
    def test_issues_foreground_request_when_window_found(self, manager):
        fake_hwnd = 4242
        calls = {"set_foreground": 0, "restore": 0}

        fake_win32gui = MagicMock()
        fake_win32gui.IsIconic.return_value = False
        fake_win32gui.SetForegroundWindow.side_effect = lambda hwnd: calls.__setitem__(
            "set_foreground", calls["set_foreground"] + 1
        )
        fake_win32con = MagicMock(SW_RESTORE=9)
        fake_win32process = MagicMock()
        fake_win32process.GetWindowThreadProcessId.return_value = (111, 222)
        fake_win32process.AttachThreadInput.return_value = True
        fake_win32api = MagicMock()
        fake_win32api.GetCurrentThreadId.return_value = 999

        with patch.object(chrome_session, "_find_main_window_hwnd", return_value=fake_hwnd), \
             patch.dict(sys.modules, {
                 "win32gui": fake_win32gui,
                 "win32con": fake_win32con,
                 "win32process": fake_win32process,
                 "win32api": fake_win32api,
             }):
            result = manager.bring_to_foreground()

        assert result is True
        assert calls["set_foreground"] == 1
        # thread input was attached then detached around the call
        assert fake_win32process.AttachThreadInput.call_count == 2

    def test_minimized_window_is_restored_first(self, manager):
        fake_hwnd = 5555
        fake_win32gui = MagicMock()
        fake_win32gui.IsIconic.return_value = True
        fake_win32con = MagicMock(SW_RESTORE=9)
        fake_win32process = MagicMock()
        fake_win32process.GetWindowThreadProcessId.return_value = (111, 111)  # same thread
        fake_win32api = MagicMock()
        fake_win32api.GetCurrentThreadId.return_value = 111

        with patch.object(chrome_session, "_find_main_window_hwnd", return_value=fake_hwnd), \
             patch.dict(sys.modules, {
                 "win32gui": fake_win32gui,
                 "win32con": fake_win32con,
                 "win32process": fake_win32process,
                 "win32api": fake_win32api,
             }):
            result = manager.bring_to_foreground()

        assert result is True
        fake_win32gui.ShowWindow.assert_called_once_with(fake_hwnd, 9)

    def test_pywin32_unavailable_returns_false_not_raises(self, manager):
        # Simulate the imports failing by removing them from sys.modules
        # and blocking re-import.
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name in ("win32gui", "win32con", "win32process", "win32api"):
                raise ImportError(f"no {name}")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            result = manager.bring_to_foreground()
        assert result is False


class TestFindMainWindowHwnd:
    def test_only_matches_our_own_automation_process_pids(self):
        engine = {"name": "chrome", "process_name": "chrome.exe"}
        our_proc = MagicMock(pid=100)

        fake_win32gui = MagicMock()
        fake_win32gui.IsWindowVisible.return_value = True
        fake_win32gui.GetWindowText.return_value = "YouTube - Google Chrome"

        fake_win32process = MagicMock()
        # Two windows enumerate: one belongs to pid 100 (ours), one to pid 999 (unrelated)
        def enum_windows(callback, extra):
            callback(111, extra)  # will resolve to pid 100
            callback(222, extra)  # will resolve to pid 999

        fake_win32gui.EnumWindows.side_effect = enum_windows

        def get_pid(hwnd):
            return (0, 100) if hwnd == 111 else (0, 999)

        fake_win32process.GetWindowThreadProcessId.side_effect = get_pid

        with patch.object(chrome_session, "_automation_processes", return_value=[our_proc]), \
             patch.dict(sys.modules, {
                 "win32gui": fake_win32gui,
                 "win32process": fake_win32process,
                 "psutil": MagicMock(),
             }):
            hwnd = chrome_session._find_main_window_hwnd(engine)

        assert hwnd == 111  # only the window belonging to our own pid

    def test_returns_none_when_no_automation_processes(self):
        engine = {"name": "chrome", "process_name": "chrome.exe"}
        with patch.object(chrome_session, "_automation_processes", return_value=[]):
            assert chrome_session._find_main_window_hwnd(engine) is None