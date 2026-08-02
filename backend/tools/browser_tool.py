"""
Browser tool
============
Replaces the old hardcoded "open_app" branch of the system tool with a
proper browser tool: named sites, arbitrary URLs, and search across a
handful of engines.
"""

from __future__ import annotations

import subprocess
import webbrowser
from urllib.parse import quote_plus

import pyautogui

from agent.registry import ToolResult, action
from config.settings import BROWSER_EXES as _BROWSER_EXES
from utils.logger import get_logger

logger = get_logger(__name__)

TOOL_DESCRIPTION = "Open the browser, a named website, an arbitrary URL, or run a web search."

_BROWSER_PROCESS_NAMES = {"chrome.exe", "msedge.exe", "brave.exe", "firefox.exe", "opera.exe"}

_SITES = {
    "youtube": "https://youtube.com",
    "instagram": "https://instagram.com",
    "facebook": "https://facebook.com",
    "gmail": "https://mail.google.com",
    "outlook": "https://outlook.com",
    "teams": "https://teams.microsoft.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "gemini": "https://gemini.google.com",
    "github": "https://github.com",
    "linkedin": "https://linkedin.com",
    "spotify": "https://open.spotify.com",
    "netflix": "https://netflix.com",
    "amazon": "https://amazon.in",
    "flipkart": "https://flipkart.com",
    "imdb": "https://imdb.com",
    "stackoverflow": "https://stackoverflow.com",
    "google": "https://google.com",
    "duckduckgo": "https://duckduckgo.com",
    "maps": "https://maps.google.com",
    "calendar": "https://calendar.google.com",
}

_SEARCH_ENGINES = {
    "google": "https://www.google.com/search?q={q}",
    "bing": "https://www.bing.com/search?q={q}",
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={q}",
    "duckduckgo": "https://duckduckgo.com/?q={q}",
}


@action("browser", "open", "Open the default browser.", tool_description=TOOL_DESCRIPTION)
def open_browser() -> ToolResult:
    webbrowser.open("https://google.com")
    return ToolResult(True, "Opening your browser.")


@action("browser", "open_app", "Open a specific browser (chrome, edge, brave, firefox).", required_args=["browser"])
def open_specific_browser(browser: str) -> ToolResult:
    key = browser.strip().lower()
    exe = _BROWSER_EXES.get(key)
    if exe:
        try:
            subprocess.Popen(exe)
            return ToolResult(True, f"Opening {browser.title()}.")
        except FileNotFoundError:
            pass
    # Fallback: let the OS pick, or just open the default browser.
    try:
        subprocess.Popen(key, shell=True)
        return ToolResult(True, f"Opening {browser.title()}.")
    except Exception:
        webbrowser.open("https://google.com")
        return ToolResult(True, f"Couldn't find {browser.title()} specifically, opened your default browser instead.")


@action("browser", "open_site", "Open a known website by name.", required_args=["site"])
def open_site(site: str) -> ToolResult:
    key = site.strip().lower()
    if key in _SITES:
        webbrowser.open(_SITES[key])
        return ToolResult(True, f"Opening {site.title()}.")
    return open_url(site)


@action("browser", "open_url", "Open an arbitrary URL.", required_args=["url"])
def open_url(url: str) -> ToolResult:
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    webbrowser.open(url)
    return ToolResult(True, f"Opening {url}.")


@action("browser", "search", "Run a web search (default engine: Google).", required_args=["query"])
def search(query: str, engine: str = "google") -> ToolResult:
    key = engine.strip().lower()
    template = _SEARCH_ENGINES.get(key, _SEARCH_ENGINES["google"])
    webbrowser.open(template.format(q=quote_plus(query)))
    return ToolResult(True, f"Searching {key.title()} for \"{query}\".")


def _foreground_browser_title() -> str | None:
    """Return the foreground window's title if it belongs to a known
    browser process, else None. Used to avoid blindly sending Ctrl+W to
    whatever window happens to have focus."""
    try:
        import psutil
        import win32gui
        import win32process
    except ImportError:
        return None

    hwnd = win32gui.GetForegroundWindow()
    title = win32gui.GetWindowText(hwnd)
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process_name = psutil.Process(pid).name().lower()
    except Exception as exc:
        logger.warning("Couldn't identify foreground process: %s", exc)
        return None

    return title if process_name in _BROWSER_PROCESS_NAMES else None


def _verify_close_tab(args: Dict[str, Any], result: Any) -> Optional[bool]:
    """True if the foreground window's title actually changed from the one
    we captured right before sending Ctrl+W. Chrome/Edge/Firefox set the OS
    window title to the active tab's page title, so a real tab close changes
    it (to whatever tab became active next, or the browser closes entirely).
    If the title is exactly unchanged, Ctrl+W most likely never landed.
    """
    data = getattr(result, "data", None) or {}
    closed_title = data.get("closed_title")
    if not closed_title:
        return None  # nothing captured to compare against (e.g. action failed before this point)

    try:
        import win32gui
    except ImportError:
        return None

    try:
        current_title = win32gui.GetWindowText(win32gui.GetForegroundWindow())
    except Exception as exc:
        logger.debug("close_tab verifier couldn't read foreground title: %s", exc)
        return None

    return current_title != closed_title


@action(
    "browser", "close_tab",
    "Close the current browser tab — best effort, only acts when a "
    "recognized browser window is actually focused.",
    verify=_verify_close_tab, max_retries=1,
)
def close_tab() -> ToolResult:
    """Sends Ctrl+W to the foreground window — but only when that window
    is confirmed to belong to a real browser process, so a request like
    "close chatgpt" can't accidentally close a tab/window in some other
    unrelated app that happened to have focus.

    Real limitation: this closes whichever tab currently has focus in that
    browser, not specifically "the ChatGPT tab" — Python has no handle back
    to a tab that was opened via a plain OS-level browser launch, so it
    can't target a specific tab among several open ones.
    """
    title = _foreground_browser_title()
    if not title:
        return ToolResult(
            False,
            "The focused window right now isn't a recognized browser, so I won't "
            "blindly close it — click the browser tab you want closed first, then try again.",
        )
    pyautogui.hotkey("ctrl", "w")
    return ToolResult(
        True,
        f'Closed the focused tab ("{title}").',
        data={"closed_title": title},
        speech="Closed that tab.",
    )
