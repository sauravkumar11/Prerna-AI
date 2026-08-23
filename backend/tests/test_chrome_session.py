# -*- coding: utf-8 -*-
"""
Tests for tools/chrome_session.py

The single most important property this module guarantees — and the one
with the heaviest test coverage — is that automation can NEVER terminate
or otherwise disturb the user's actual, everyday browser window (or the
window running Prerna's own frontend UI). An earlier version of this
module tried to attach to the user's real profile directly, which meant
"play a song" could silently kill the tab the user was reading. The fix
was a dedicated, separate automation profile, identified only by matching
each process's own command line for that profile's path — never by
process name alone. That's exactly what test_automation_processes_never_
match_the_users_everyday_window below proves.

Also covered: multi-engine (Chrome/Edge) auto-detection, the
PRERNA_BROWSER_ENGINE override, and per-engine profile isolation.
"""

from __future__ import annotations

import os
import unittest.mock as mock

import tools.chrome_session as cs


class _FakeProc:
    def __init__(self, name, cmdline):
        self.info = {"name": name, "cmdline": cmdline}
        self.terminated = False

    def terminate(self):
        self.terminated = True


def setup_function(_fn):
    """Clear any PRERNA_BROWSER_ENGINE override left over from a previous
    test so each test starts from a clean slate."""
    os.environ.pop("PRERNA_BROWSER_ENGINE", None)


# ── The critical safety property ────────────────────────────────────────────

def test_automation_processes_never_match_the_users_everyday_window():
    """Reproduces the exact scenario that caused a real bug: a regular
    Chrome window (the user's daily browsing, or Prerna's own frontend UI)
    running alongside a genuine automation-profile Chrome window. Only the
    automation one may ever be selected as a termination target."""
    chrome_engine = cs._engine_by_name("chrome")
    automation_dir = str(cs._automation_user_data_dir("chrome"))

    everyday_window = _FakeProc("chrome.exe", ["chrome.exe", "--profile-directory=Default"])
    automation_window = _FakeProc("chrome.exe", [
        "chrome.exe", f"--user-data-dir={automation_dir}", "--remote-debugging-port=9222",
    ])

    with mock.patch("psutil.process_iter", return_value=[everyday_window, automation_window]):
        matched = cs._automation_processes(chrome_engine)

    assert everyday_window not in matched, (
        "the user's everyday Chrome window must NEVER be a termination target"
    )
    assert automation_window in matched


def test_automation_processes_never_match_edge_everyday_window():
    """Same safety property, verified for Edge specifically — not just
    Chrome — since the multi-engine support could have reintroduced this
    per-engine if only tested against one."""
    edge_engine = cs._engine_by_name("edge")
    automation_dir = str(cs._automation_user_data_dir("edge"))

    everyday_window = _FakeProc("msedge.exe", ["msedge.exe", "--profile-directory=Default"])
    automation_window = _FakeProc("msedge.exe", [
        "msedge.exe", f"--user-data-dir={automation_dir}",
    ])

    with mock.patch("psutil.process_iter", return_value=[everyday_window, automation_window]):
        matched = cs._automation_processes(edge_engine)

    assert everyday_window not in matched
    assert automation_window in matched


def test_chrome_and_edge_automation_profiles_are_different_directories():
    """Chrome and Edge profile formats aren't interchangeable — they must
    never share a profile directory."""
    assert cs._automation_user_data_dir("chrome") != cs._automation_user_data_dir("edge")


# ── Engine auto-detection ────────────────────────────────────────────────────

def test_no_supported_browser_found_returns_none():
    with mock.patch.object(cs, "_find_engine_exe", return_value=None):
        assert cs._find_engine() is None


def test_only_edge_installed_is_auto_detected():
    def fake_find(engine):
        return "/fake/msedge.exe" if engine["name"] == "edge" else None

    with mock.patch.object(cs, "_find_engine_exe", side_effect=fake_find):
        engine = cs._find_engine()
        assert engine["name"] == "edge"


def test_both_installed_chrome_preferred_by_default():
    def fake_find(engine):
        return f"/fake/{engine['process_name']}"

    with mock.patch.object(cs, "_find_engine_exe", side_effect=fake_find):
        engine = cs._find_engine()
        assert engine["name"] == "chrome"


def test_prerna_browser_engine_override_is_honored():
    def fake_find(engine):
        return f"/fake/{engine['process_name']}"

    os.environ["PRERNA_BROWSER_ENGINE"] = "edge"
    with mock.patch.object(cs, "_find_engine_exe", side_effect=fake_find):
        engine = cs._find_engine()
        assert engine["name"] == "edge"


def test_invalid_override_falls_back_to_auto_detect():
    def fake_find(engine):
        return f"/fake/{engine['process_name']}"

    os.environ["PRERNA_BROWSER_ENGINE"] = "totally_not_a_real_engine"
    with mock.patch.object(cs, "_find_engine_exe", side_effect=fake_find):
        engine = cs._find_engine()
        assert engine["name"] == "chrome"  # falls back to default preference order


def test_override_pointing_at_uninstalled_engine_falls_back():
    """PRERNA_BROWSER_ENGINE=edge, but Edge isn't actually installed —
    must fall back to auto-detect rather than returning None."""
    def fake_find(engine):
        return "/fake/chrome.exe" if engine["name"] == "chrome" else None

    os.environ["PRERNA_BROWSER_ENGINE"] = "edge"
    with mock.patch.object(cs, "_find_engine_exe", side_effect=fake_find):
        engine = cs._find_engine()
        assert engine["name"] == "chrome"


# ── Session manager behavior ─────────────────────────────────────────────────

def test_close_browser_does_not_call_quit():
    """close_browser() must release our handle WITHOUT calling
    driver.quit() — quit() would close every tab in the user's real
    browser when attached via debugger_address, which defeats the entire
    point of this module."""
    session = cs.ChromeSessionManager()
    fake_driver = mock.Mock()
    session._driver = fake_driver

    session.close_browser()

    fake_driver.quit.assert_not_called()
    assert session._driver is None


def test_get_chrome_session_is_a_singleton():
    s1 = cs.get_chrome_session()
    s2 = cs.get_chrome_session()
    assert s1 is s2


def test_is_alive_false_when_driver_raises():
    fake_driver = mock.Mock()
    type(fake_driver).window_handles = mock.PropertyMock(side_effect=Exception("dead"))
    assert cs.ChromeSessionManager._is_alive(fake_driver) is False


def test_is_alive_true_when_driver_responds():
    fake_driver = mock.Mock()
    fake_driver.window_handles = ["a"]
    assert cs.ChromeSessionManager._is_alive(fake_driver) is True