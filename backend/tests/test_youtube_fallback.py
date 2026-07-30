# -*- coding: utf-8 -*-
"""
Tests for tools/youtube_tool.py's _url_fallback().

Regression test for a real production crash: when tools/chrome_session.py
was rewritten to support multiple browser engines (Chrome and Edge), the
standalone `_find_chrome_exe()` function was replaced by `_find_engine()`
(which returns an engine dict, not a bare path). youtube_tool.py's fallback
path was never updated to match, and crashed with:

    ImportError: cannot import name '_find_chrome_exe' from 'tools.chrome_session'

every time full Selenium automation failed and the fallback path ran —
confirmed via a real production trace log. The system recovered anyway
(agent.goal_loop's retry logic re-planned and eventually succeeded a
different way), but that's masking a real bug behind extra latency and a
logged exception, not actually working correctly.
"""

from __future__ import annotations

import unittest.mock as mock

import tools.youtube_tool as yt


def test_url_fallback_does_not_import_removed_function():
    """The core regression check: this must not raise ImportError."""
    with mock.patch(
        "tools.chrome_session._find_engine",
        return_value={"name": "chrome", "display_name": "Google Chrome", "exe_path": "/fake/chrome.exe"},
    ), mock.patch("subprocess.Popen") as mock_popen:
        result = yt._url_fallback("some song", reason="selenium failed")
        assert result.success is True
        mock_popen.assert_called_once()


def test_url_fallback_launches_detected_engine_exe_with_search_url():
    with mock.patch(
        "tools.chrome_session._find_engine",
        return_value={"name": "edge", "display_name": "Microsoft Edge", "exe_path": "/fake/msedge.exe"},
    ), mock.patch("subprocess.Popen") as mock_popen:
        yt._url_fallback("dilbar song")
        args = mock_popen.call_args[0][0]
        assert args[0] == "/fake/msedge.exe"
        assert "dilbar" in args[1] or "dilbar+song" in args[1] or "dilbar%20song" in args[1] or "dilbar song".replace(" ", "+") in args[1]


def test_url_fallback_falls_back_to_webbrowser_when_no_engine_found():
    with mock.patch("tools.chrome_session._find_engine", return_value=None), \
         mock.patch("webbrowser.open") as mock_open:
        result = yt._url_fallback("some song")
        assert result.success is True
        mock_open.assert_called_once()


def test_url_fallback_message_includes_the_given_reason():
    with mock.patch(
        "tools.chrome_session._find_engine",
        return_value={"name": "chrome", "display_name": "Google Chrome", "exe_path": "/fake/chrome.exe"},
    ), mock.patch("subprocess.Popen"):
        result = yt._url_fallback("some song", reason="InvalidSessionIdException: session deleted")
        assert "InvalidSessionIdException" in result.message


def test_url_fallback_survives_popen_failure():
    """Even if launching the detected engine's exe itself fails (e.g. the
    path is stale), must fall back to webbrowser.open rather than crash."""
    with mock.patch(
        "tools.chrome_session._find_engine",
        return_value={"name": "chrome", "display_name": "Google Chrome", "exe_path": "/fake/chrome.exe"},
    ), mock.patch("subprocess.Popen", side_effect=OSError("file not found")), \
         mock.patch("webbrowser.open") as mock_open:
        result = yt._url_fallback("some song")
        assert result.success is True
        mock_open.assert_called_once()