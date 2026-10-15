"""
System tool
===========
Power/session control, display/appearance toggles, and a generic launcher
for common Windows apps (calculator, paint, task manager, etc.) - see
config.WINDOWS_APPS for the full list.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
from datetime import datetime
from typing import Dict, List

from agent.registry import ToolResult, action
from config.settings import WINDOWS_APPS
from utils.logger import get_logger

logger = get_logger(__name__)

TOOL_DESCRIPTION = (
    "Control the computer's power/session state (lock, shutdown, restart, sleep), "
    "display appearance (dark/light mode, night light, brightness), and open common "
    "Windows apps (calculator, paint, task manager, control panel, ...)."
)


@action("system", "time", "Tell the current time.")
def get_time() -> ToolResult:
    """No OS call, no LLM call — just datetime.now(). Gemini isn't a
    real-time clock, so routing 'what's the time' through a full chat
    turn was previously both slower AND less reliably correct than this."""
    now = datetime.now().strftime("%I:%M %p").lstrip("0")
    return ToolResult(True, f"It's {now}.")


@action("system", "date", "Tell today's date.")
def get_date() -> ToolResult:
    today = datetime.now().strftime("%A, %B %d")
    return ToolResult(True, f"It's {today}.")


@action("system", "lock", "Lock the computer.", tool_description=TOOL_DESCRIPTION)
def lock() -> ToolResult:
    ctypes.windll.user32.LockWorkStation()
    return ToolResult(True, "Locking your laptop.")


@action("system", "shutdown", "Shut down the computer.", dangerous=True)
def shutdown() -> ToolResult:
    os.system("shutdown /s /t 10")
    return ToolResult(True, "Shutting down your laptop in 10 seconds.")


@action("system", "restart", "Restart the computer.", dangerous=True)
def restart() -> ToolResult:
    os.system("shutdown /r /t 10")
    return ToolResult(True, "Restarting your laptop in 10 seconds.")


@action("system", "cancel_shutdown", "Cancel a pending shutdown/restart.")
def cancel_shutdown() -> ToolResult:
    os.system("shutdown /a")
    return ToolResult(True, "Cancelled the pending shutdown.")


@action("system", "sleep", "Put the computer to sleep.")
def sleep() -> ToolResult:
    os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
    return ToolResult(True, "Putting your laptop to sleep.")


@action("system", "hibernate", "Hibernate the computer.")
def hibernate() -> ToolResult:
    os.system("shutdown /h")
    return ToolResult(True, "Hibernating your laptop.")


@action("system", "logout", "Log out of the current Windows session.", dangerous=True)
def logout() -> ToolResult:
    os.system("shutdown /l")
    return ToolResult(True, "Logging you out.")


def _set_apps_theme(light: bool) -> bool:
    try:
        value = 1 if light else 0
        subprocess.run(
            [
                "powershell", "-Command",
                "Set-ItemProperty -Path "
                "'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize' "
                f"-Name AppsUseLightTheme -Value {value}",
            ],
            capture_output=True, timeout=10,
        )
        return True
    except Exception:
        return False


@action("system", "dark_mode", "Switch Windows to dark mode.")
def dark_mode() -> ToolResult:
    if _set_apps_theme(light=False):
        return ToolResult(True, "Switched to dark mode. You may need to reopen some apps to see it.")
    return ToolResult(False, "Couldn't switch the theme.")


@action("system", "light_mode", "Switch Windows to light mode.")
def light_mode() -> ToolResult:
    if _set_apps_theme(light=True):
        return ToolResult(True, "Switched to light mode. You may need to reopen some apps to see it.")
    return ToolResult(False, "Couldn't switch the theme.")


@action("system", "night_light_on", "Turn on Night Light (warmer screen colors).")
def night_light_on() -> ToolResult:
    subprocess.Popen("start ms-settings:nightlight", shell=True)
    return ToolResult(True, "Opened Night Light settings - toggle it on there (Windows doesn't expose a direct command for this).")


@action("system", "brightness", "Set screen brightness (0-100).", required_args=["level"])
def set_brightness(level: int) -> ToolResult:
    try:
        pct = max(0, min(100, int(level)))
    except (TypeError, ValueError):
        return ToolResult(False, "Brightness needs to be a number between 0 and 100.")

    result = subprocess.run(
        [
            "powershell", "-Command",
            "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)."
            f"WmiSetBrightness(1,{pct})",
        ],
        capture_output=True, timeout=10,
    )
    if result.returncode == 0:
        return ToolResult(True, f"Set brightness to {pct}%.")
    return ToolResult(False, "Couldn't change brightness - your display/drivers may not support it.")


@action("system", "airplane_mode_on", "Turn airplane mode on (best effort).")
def airplane_mode_on() -> ToolResult:
    subprocess.Popen("start ms-settings:network-airplanemode", shell=True)
    return ToolResult(True, "Opened airplane mode settings - Windows doesn't expose a reliable direct toggle for this.")


@action("system", "airplane_mode_off", "Turn airplane mode off (best effort).")
def airplane_mode_off() -> ToolResult:
    subprocess.Popen("start ms-settings:network-airplanemode", shell=True)
    return ToolResult(True, "Opened airplane mode settings - Windows doesn't expose a reliable direct toggle for this.")


@action("system", "open_app", "Open a common Windows app by name (calculator, paint, task manager, ...).", required_args=["app"])
def open_app(app: str) -> ToolResult:
    key = app.strip().lower()
    command = WINDOWS_APPS.get(key)

    if not command:
        # Fuzzy fallback: "microsoft store" should still match the "store"
        # mapping, "windows terminal" should match "terminal", etc. — exact
        # key match only was too strict for how people actually phrase these.
        for known_key, known_command in WINDOWS_APPS.items():
            if known_key in key or key in known_key:
                command = known_command
                break

    if not command:
        return ToolResult(False, f"I don't have '{app}' mapped to an app yet.")
    subprocess.Popen(command, shell=True)
    return ToolResult(True, f"Opening {app.title()}.")


# ── v1.2.1 Bug 2: close an app/window by name, safely ───────────────────
#
# Symptom: "Close Chrome", "Close Downloads", "Close File Explorer" would
# sometimes close Prerna herself instead of the named target.
#
# Root cause (confirmed this session): there was no registered close-by-name
# action anywhere in the codebase at all (grepped the full backend for
# "close"/"taskkill"/"terminate"/"WM_CLOSE"/"kill" — only camera_tool.py's
# single-app close_camera and browser_tool.py's focused-tab close_tab
# exist). Whatever previously produced the "closes Prerna" symptom was an
# improvised fallback outside any reviewed tool file, not a targeting bug
# in existing logic — so this is new functionality, not a patch.
#
# Design principle: Prerna's own windows are excluded from candidates
# STRUCTURALLY, at enumeration time (by PID, in _enum_visible_windows),
# not by name-matching heuristics. That guarantees she can never be an
# accidental match for any app name whatsoever, rather than relying on
# every future app-name pattern to avoid colliding with her own title.

# Names that mean "close Prerna herself" — handled as an explicit, separate
# refusal rather than ever being treated as an app to search for, since
# self-closing is a deliberate decision this tool does not perform.
_SELF_CLOSE_NAMES = {"prerna", "yourself", "this app", "this program"}

# Process image names to check for apps whose WINDOWS_APPS launch command
# doesn't match their actual running process name (e.g. "calc" launches
# CalculatorApp.exe on modern Windows, not calc.exe), or that aren't in
# WINDOWS_APPS at all (browsers are launched via browser_tool/chrome_session,
# not system_tool.open_app).
_APP_PROCESS_HINTS: Dict[str, List[str]] = {
    "chrome": ["chrome.exe"],
    "google chrome": ["chrome.exe"],
    "edge": ["msedge.exe"],
    "microsoft edge": ["msedge.exe"],
    "notepad": ["notepad.exe"],
    "paint": ["mspaint.exe"],
    "calculator": ["calculatorapp.exe", "calc.exe"],
    "task manager": ["taskmgr.exe"],
    "cmd": ["cmd.exe"],
    "command prompt": ["cmd.exe"],
    "powershell": ["powershell.exe", "pwsh.exe"],
    "terminal": ["windowsterminal.exe", "wt.exe"],
    "spotify": ["spotify.exe"],
    "whatsapp": ["whatsapp.exe"],
    "vscode": ["code.exe"],
    "vs code": ["code.exe"],
    "visual studio code": ["code.exe"],
    "word": ["winword.exe"],
    "excel": ["excel.exe"],
    "powerpoint": ["powerpnt.exe"],
}


def _enum_visible_windows() -> List[dict]:
    """Best-effort enumeration of visible top-level windows, each as
    {"hwnd", "title", "process_name", "pid"}.

    Returns [] if pywin32/psutil aren't available, same "unknown, not an
    error" convention as window_tool.get_active_window_info.

    SAFETY-CRITICAL: any window belonging to our own process (by PID) is
    skipped here, unconditionally, before it's ever added to the returned
    list. This is the actual fix for Bug 2 — every caller downstream of
    this function is structurally incapable of matching Prerna's own
    windows, regardless of what app name was searched for.
    """
    try:
        import psutil
        import win32gui
        import win32process
    except ImportError:
        logger.warning("pywin32/psutil not available — window enumeration skipped")
        return []

    own_pid = os.getpid()
    windows: List[dict] = []

    def _callback(hwnd, _extra):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd).strip()
        if not title:
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            return
        if pid == own_pid:
            return  # never a candidate — this is our own process's window
        try:
            process_name = psutil.Process(pid).name()
        except Exception:
            process_name = ""
        windows.append({"hwnd": hwnd, "title": title, "process_name": process_name, "pid": pid})

    win32gui.EnumWindows(_callback, None)
    return windows


def _matches_app(window: dict, app_key: str, hints: List[str]) -> bool:
    process_l = window["process_name"].lower()
    title_l = window["title"].lower()
    if hints and any(hint in process_l for hint in hints):
        return True
    return app_key in title_l


@action(
    "system", "close_app",
    "Close an app or window by name (e.g. 'close chrome', 'close downloads', "
    "'close file explorer'). Closes the matching window(s) gracefully; never "
    "targets Prerna's own process unless explicitly asked to close Prerna herself.",
    required_args=["app"],
)
def close_app(app: str) -> ToolResult:
    key = app.strip().lower()

    if key in _SELF_CLOSE_NAMES:
        return ToolResult(
            False,
            "I won't close myself from a general close command — if you want to stop "
            "me, please close me from the terminal or task tray directly.",
        )

    windows = _enum_visible_windows()
    if not windows:
        return ToolResult(
            False,
            "I couldn't inspect open windows on this machine right now, so I can't "
            "safely find and close it.",
        )

    hints = _APP_PROCESS_HINTS.get(key, [])
    matches = [w for w in windows if _matches_app(w, key, hints)]

    if not matches:
        return ToolResult(False, f"I couldn't find an open window matching '{app}'.")

    try:
        import win32con
        import win32gui
    except ImportError:
        return ToolResult(False, "I found a match but can't send a close signal (pywin32 unavailable).")

    closed_titles: List[str] = []
    for w in matches:
        try:
            win32gui.PostMessage(w["hwnd"], win32con.WM_CLOSE, 0, 0)
            closed_titles.append(w["title"])
        except Exception as exc:
            logger.warning("Couldn't close window '%s': %s", w["title"], exc)

    if not closed_titles:
        return ToolResult(False, f"I found '{app}' but couldn't close it — it may need to be closed by hand.")

    if len(closed_titles) == 1:
        return ToolResult(True, f"Closed {closed_titles[0]}.", speech="Closed it.")
    return ToolResult(
        True,
        f"Closed {len(closed_titles)} window(s) matching '{app}': " + ", ".join(closed_titles),
        speech=f"Closed {len(closed_titles)} windows.",
    )