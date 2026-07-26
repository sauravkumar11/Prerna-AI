"""
YouTube tool
============
Two modes:

1. URL-based (no dependency): search, open, transport controls via media keys.
2. Selenium-based: play_first_result actually clicks the first video and plays it.
   Falls back to URL mode gracefully if Chrome/ChromeDriver isn't available.

Install once on your machine:
    pip install selenium webdriver-manager
ChromeDriver is auto-downloaded by webdriver-manager the first time.
"""

from __future__ import annotations

import ctypes
import re
import subprocess
import threading
import time
import webbrowser
from urllib.parse import quote_plus

from agent.registry import ToolResult, action
from memory.memory_manager import remember, load_memory
from tools.chrome_session import get_chrome_session, open_in_new_tab
from utils.logger import get_logger

logger = get_logger(__name__)

TOOL_DESCRIPTION = "Search YouTube, auto-play the first result, and control playback."

# Common trailing noise in YouTube music video titles — stripped so TTS
# says just the song name instead of reading the full credits line
# (e.g. "Dilbar Lyrical | Satyameva Jayate | John Abraham..." -> "Dilbar").
_TITLE_NOISE_SUFFIXES = [
    "official music video", "official video", "official audio",
    "full video song", "full song", "title song", "title track",
    "lyrical video", "lyrics video", "video song", "lyrical",
    "lyrics", "audio", "video", "song",
]


def _short_title(title: str) -> str:
    """Extract a short, speech-friendly title from a full YouTube title.

    YouTube music video titles are usually
    "<Song Name> <noise> | <Movie> | <Cast/Singers/Composers>" — this keeps
    only the song name for TTS, while the full title still goes in the
    on-screen chat message.
    """
    if not title:
        return title
    short = re.split(r"\s*\|\s*", title, maxsplit=1)[0]
    short = re.split(r"\s+-\s+", short, maxsplit=1)[0]
    short = short.strip()

    lowered = short.lower()
    changed = True
    while changed:
        changed = False
        for suffix in _TITLE_NOISE_SUFFIXES:
            # Require a word boundary before the suffix (start-of-string or
            # a non-alphanumeric char) so we only strip whole trailing words,
            # never truncate mid-word.
            if lowered.endswith(suffix) and (
                len(lowered) == len(suffix) or not lowered[-len(suffix) - 1].isalnum()
            ):
                short = short[: -len(suffix)].strip()
                lowered = short.lower()
                changed = True
    return short or title


VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_VOLUME_UP        = 0xAF
VK_VOLUME_DOWN      = 0xAE
KEYEVENTF_KEYUP     = 0x0002

# Tracks *why* the last driver-start attempt failed, so the fallback
# message can tell the user the real reason instead of always guessing
# "selenium isn't installed" (which is often wrong — e.g. Chrome not
# found, or the debug port never came up).
_last_driver_error: str | None = None


def _press(vk_code: int, times: int = 1) -> None:
    for _ in range(times):
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.04)


def _get_driver():
    """Return the shared, real-profile Chrome driver (attached to the
    user's own signed-in browser via ChromeSessionManager), starting or
    reattaching it if needed. Returns None if Chrome truly can't be
    reached — check `_last_driver_error` for why.

    This is no longer a locally-owned throwaway driver: every tool that
    needs browser automation goes through the same shared session, so
    "search youtube" then "open gmail" then "search google" all happen in
    the SAME already-signed-in Chrome window/tab, not a fresh blank
    profile each time.
    """
    global _last_driver_error
    session = get_chrome_session()
    driver = session.get_browser()
    _last_driver_error = session.last_error
    return driver


_AD_SKIP_SELECTORS = [
    ".ytp-ad-skip-button-modern",
    ".ytp-ad-skip-button",
    ".ytp-skip-ad-button",
]


def _skip_ads_in_background(driver, duration: float = 90.0, poll_interval: float = 1.0) -> None:
    """Watch for YouTube's "Skip Ad" button and click it whenever it shows up.

    Runs in a daemon thread so it never blocks the HTTP response back to the
    user. Videos can have multiple ad breaks (pre-roll and mid-roll), so this
    keeps polling for `duration` seconds rather than checking just once.
    Non-skippable ads simply have no matching button, so those are left alone.
    """

    def _worker() -> None:
        from selenium.webdriver.common.by import By

        deadline = time.time() + duration
        while time.time() < deadline:
            try:
                for selector in _AD_SKIP_SELECTORS:
                    for btn in driver.find_elements(By.CSS_SELECTOR, selector):
                        if btn.is_displayed():
                            # JS click: same click-interception issue as the
                            # main video click can happen with the player's
                            # own overlay controls fading in/out.
                            driver.execute_script("arguments[0].click();", btn)
                            logger.info("Skipped a YouTube ad.")
                            time.sleep(1.0)
            except Exception:
                # Window/tab closed or navigated away — stop watching quietly
                return
            time.sleep(poll_interval)

    threading.Thread(target=_worker, daemon=True).start()


def _selenium_play_first(query: str) -> ToolResult:
    """Open YouTube search and click the first non-ad video result."""
    driver = _get_driver()
    if driver is None:
        return _url_fallback(query, reason=_last_driver_error)

    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        open_in_new_tab(driver, url)

        # Wait for video thumbnails to load
        wait = WebDriverWait(driver, 12)
        wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "ytd-video-renderer #video-title")
        ))
        time.sleep(1.0)  # let ads/promos settle

        # Click the first real video (skip promoted/ad results)
        videos = driver.find_elements(By.CSS_SELECTOR, "ytd-video-renderer #video-title")
        if not videos:
            return _url_fallback(query, reason="no video results were found on the page")

        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
            videos[0],
        )
        time.sleep(0.3)  # let smooth-scroll settle before clicking
        try:
            videos[0].click()
        except Exception as click_exc:
            # Sticky header/overlay intercepted the pointer click — a JS
            # click bypasses the visual hit-test and works regardless.
            logger.warning(
                "Direct click intercepted (%s), falling back to JS click.",
                click_exc,
            )
            driver.execute_script("arguments[0].click();", videos[0])

        # Wait for the player to load
        try:
            wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "video.html5-main-video")
            ))
        except Exception:
            pass  # player might already be playing

        title = videos[0].get_attribute("title") or query
        logger.info("Playing YouTube: %s", title)
        _skip_ads_in_background(driver)
        return ToolResult(
            True,
            f'Playing "{title}" on YouTube.',
            speech=f"Playing {_short_title(title)}.",
        )

    except Exception as exc:
        logger.warning("Selenium YouTube failed: %s", exc)
        return _url_fallback(query, reason=f"{type(exc).__name__}: {exc}")


def _url_fallback(query: str, reason: str | None = None) -> ToolResult:
    url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"

    # Open in Chrome specifically — webbrowser.open() defers to the OS
    # default browser, which on this machine is Microsoft Edge, not
    # Chrome. That silently broke the fallback: the search would open in
    # Edge, a browser this tool never automates, so nothing would ever
    # auto-play from it. Launching chrome.exe directly with the URL
    # guarantees it at least lands in the right browser, even on the path
    # where full automation isn't available this time.
    from tools.chrome_session import _find_chrome_exe
    chrome_exe = _find_chrome_exe()
    if chrome_exe:
        try:
            subprocess.Popen([chrome_exe, url])
        except Exception as exc:
            logger.warning("Couldn't launch Chrome directly (%s) — falling back to OS default browser.", exc)
            webbrowser.open(url)
    else:
        webbrowser.open(url)

    if reason:
        message = (
            f'Opened YouTube search for "{query}". '
            f"Auto-play didn't start — {reason}."
        )
    else:
        message = (
            f'Opened YouTube search for "{query}". '
            "Install selenium and webdriver-manager to auto-play the first result next time."
        )
    return ToolResult(True, message)


# ── Actions ───────────────────────────────────────────────────────────────────

@action("youtube", "open", "Open YouTube homepage.", tool_description=TOOL_DESCRIPTION)
def open_youtube() -> ToolResult:
    driver = _get_driver()
    if driver:
        open_in_new_tab(driver, "https://youtube.com")
        return ToolResult(True, "Opening YouTube.")
    webbrowser.open("https://youtube.com")
    return ToolResult(True, "Opening YouTube.")


@action("youtube", "search", "Search YouTube and auto-play the first result.", required_args=["query"])
def search(query: str) -> ToolResult:
    remember("last_youtube_query", query)
    return _selenium_play_first(query)


@action(
    "youtube",
    "play_first_result",
    "Play the first result for a query, or reuse the last search if no query given.",
)
def play_first_result(query: str = "") -> ToolResult:
    if not query:
        query = load_memory().get("last_youtube_query", "")
    if not query:
        return ToolResult(False, "What should I search for on YouTube?")
    remember("last_youtube_query", query)
    return _selenium_play_first(query)


@action("youtube", "play_pause", "Toggle play/pause.")
def play_pause() -> ToolResult:
    driver = _get_driver()
    if driver:
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
            body = driver.find_element(By.TAG_NAME, "body")
            body.send_keys(Keys.SPACE)
            return ToolResult(True, "Toggled play/pause.")
        except Exception:
            pass
    _press(VK_MEDIA_PLAY_PAUSE)
    return ToolResult(True, "Toggled play/pause.")


@action("youtube", "next", "Skip to next video.")
def next_track() -> ToolResult:
    _press(VK_MEDIA_NEXT_TRACK)
    return ToolResult(True, "Skipped to next.")


@action("youtube", "previous", "Go to previous video.")
def previous_track() -> ToolResult:
    _press(VK_MEDIA_PREV_TRACK)
    return ToolResult(True, "Went back.")


@action("youtube", "volume_up", "Turn volume up.")
def volume_up() -> ToolResult:
    driver = _get_driver()
    if driver:
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
            body = driver.find_element(By.TAG_NAME, "body")
            for _ in range(5):
                body.send_keys(Keys.ARROW_UP)
            return ToolResult(True, "Volume up.")
        except Exception:
            pass
    _press(VK_VOLUME_UP, 5)
    return ToolResult(True, "Volume up.")


@action("youtube", "volume_down", "Turn volume down.")
def volume_down() -> ToolResult:
    driver = _get_driver()
    if driver:
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
            body = driver.find_element(By.TAG_NAME, "body")
            for _ in range(5):
                body.send_keys(Keys.ARROW_DOWN)
            return ToolResult(True, "Volume down.")
        except Exception:
            pass
    _press(VK_VOLUME_DOWN, 5)
    return ToolResult(True, "Volume down.")


@action("youtube", "skip_ad", "Skip the current YouTube ad.")
def skip_ad() -> ToolResult:
    driver = _get_driver()
    if driver is None:
        return ToolResult(False, "Browser automation not available to skip ads.")
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        wait = WebDriverWait(driver, 8)
        skip_btn = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, ".ytp-skip-ad-button, .ytp-ad-skip-button")
        ))
        skip_btn.click()
        return ToolResult(True, "Ad skipped.")
    except Exception:
        return ToolResult(False, "No skippable ad found right now.")


@action("youtube", "fullscreen", "Toggle fullscreen.")
def fullscreen() -> ToolResult:
    driver = _get_driver()
    if driver:
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
            body = driver.find_element(By.TAG_NAME, "body")
            body.send_keys("f")
            return ToolResult(True, "Toggled fullscreen.")
        except Exception:
            pass
    return ToolResult(False, "Couldn't toggle fullscreen.")