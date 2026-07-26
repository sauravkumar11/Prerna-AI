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

from agent.registry import ToolResult, action
from config.settings import WINDOWS_APPS

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