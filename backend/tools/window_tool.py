"""
Window tool
===========
Exposes the current foreground ("active") window — title + owning process —
both as a directly askable action ("which window is open right now?") and
as a small helper (`get_active_window_info`) that other modules (the
planner's context) can import to make Prerna aware of on-screen context
without her having to be told explicitly every time.
"""

from __future__ import annotations

from typing import Optional, TypedDict

from agent.registry import ToolResult, action
from utils.logger import get_logger

logger = get_logger(__name__)

TOOL_DESCRIPTION = "Find out what window/app is currently focused on screen."


class ActiveWindowInfo(TypedDict):
    title: str
    process: str


def get_active_window_info() -> Optional[ActiveWindowInfo]:
    """Best-effort lookup of the foreground window's title and owning
    process name. Returns None if pywin32/psutil aren't available or no
    window is currently focused — callers should treat that as
    "unknown", not as an error."""
    try:
        import psutil
        import win32gui
        import win32process
    except ImportError:
        logger.warning("pywin32/psutil not available — active window lookup skipped")
        return None

    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        title = win32gui.GetWindowText(hwnd).strip()
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid).name()
    except Exception as exc:
        logger.warning("Couldn't read the active window: %s", exc)
        return None

    return {"title": title or "(untitled window)", "process": process}


@action(
    "window",
    "get_active",
    "Report which window/app is currently focused (title + process name).",
    tool_description=TOOL_DESCRIPTION,
)
def get_active() -> ToolResult:
    info = get_active_window_info()
    if not info:
        return ToolResult(False, "I couldn't tell what's on screen right now.")

    message = f"You're currently on {info['title']} ({info['process']})."
    speech = f"You're on {info['title']} right now."
    return ToolResult(True, message, data=info, speech=speech)
