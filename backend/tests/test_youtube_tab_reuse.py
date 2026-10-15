"""
Tests for v1.2.1 Bug 3: youtube_tool.py's _use_youtube_tab() tab-reuse logic.
"""
import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tools import youtube_tool  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_tab_handle():
    youtube_tool._youtube_tab_handle = None
    yield
    youtube_tool._youtube_tab_handle = None


class TestUseYoutubeTab:
    def test_first_call_opens_a_new_tab(self):
        driver = MagicMock()
        driver.window_handles = ["h1"]
        driver.current_window_handle = "h1"

        with patch.object(youtube_tool, "open_in_new_tab") as mock_open_new:
            youtube_tool._use_youtube_tab(driver, "https://youtube.com/results?search_query=x")

        mock_open_new.assert_called_once()
        assert youtube_tool._youtube_tab_handle == "h1"

    def test_second_call_reuses_existing_open_tab(self):
        driver = MagicMock()
        driver.window_handles = ["h1"]
        youtube_tool._youtube_tab_handle = "h1"

        with patch.object(youtube_tool, "open_in_new_tab") as mock_open_new:
            youtube_tool._use_youtube_tab(driver, "https://youtube.com/results?search_query=y")

        mock_open_new.assert_not_called()
        driver.switch_to.window.assert_called_once_with("h1")
        driver.get.assert_called_once_with("https://youtube.com/results?search_query=y")

    def test_reopens_new_tab_if_previous_one_was_closed(self):
        driver = MagicMock()
        driver.window_handles = ["h2"]  # "h1" is no longer open
        driver.current_window_handle = "h2"
        youtube_tool._youtube_tab_handle = "h1"

        with patch.object(youtube_tool, "open_in_new_tab") as mock_open_new:
            youtube_tool._use_youtube_tab(driver, "https://youtube.com/results?search_query=z")

        mock_open_new.assert_called_once()
        assert youtube_tool._youtube_tab_handle == "h2"

    def test_tracked_handle_updates_across_two_sequential_new_tabs(self):
        driver = MagicMock()

        driver.window_handles = ["h1"]
        driver.current_window_handle = "h1"
        with patch.object(youtube_tool, "open_in_new_tab"):
            youtube_tool._use_youtube_tab(driver, "url1")
        assert youtube_tool._youtube_tab_handle == "h1"

        # Second call: h1 still open, so it should be REUSED, not replaced.
        driver.window_handles = ["h1"]
        with patch.object(youtube_tool, "open_in_new_tab") as mock_open_new:
            youtube_tool._use_youtube_tab(driver, "url2")
        mock_open_new.assert_not_called()
        assert youtube_tool._youtube_tab_handle == "h1"


class TestSeleniumPlayFirstBringsToForeground:
    def test_calls_bring_to_foreground_before_and_after_play(self):
        fake_session = MagicMock()
        fake_driver = MagicMock()
        fake_session.get_browser.return_value = fake_driver
        fake_session.last_error = None
        fake_driver.window_handles = ["h1"]
        fake_driver.current_window_handle = "h1"

        fake_video = MagicMock()
        fake_video.get_attribute.return_value = "Some Song - Official Video"
        fake_driver.find_elements.return_value = [fake_video]

        with patch.object(youtube_tool, "get_chrome_session", return_value=fake_session), \
             patch.object(youtube_tool, "open_in_new_tab"), \
             patch("selenium.webdriver.support.ui.WebDriverWait") as mock_wait_cls:
            mock_wait_cls.return_value.until.return_value = True
            result = youtube_tool._selenium_play_first("some song")

        assert fake_session.bring_to_foreground.call_count == 2  # once before search, once after playback starts
        assert result.success