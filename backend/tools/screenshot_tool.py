"""
Screenshot tool
===============
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO

import pyautogui

from agent.registry import ToolResult, action
from config.settings import SCREENSHOT_DIR
from pathlib import Path

TOOL_DESCRIPTION = "Take a screenshot: full screen, the active window, or a specific region."


def _save(img) -> str:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    filename = datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png")
    path = SCREENSHOT_DIR / filename
    img.save(path)
    return str(path)


@action("screenshot", "default", "Take a full-screen screenshot and save it.", tool_description=TOOL_DESCRIPTION)
def take_screenshot() -> ToolResult:
    img = pyautogui.screenshot()
    path = _save(img)
    return ToolResult(True, f"Screenshot saved as {path.split(chr(92))[-1]}.", data={"path": path}, speech="Screenshot saved.")


@action("screenshot", "window", "Screenshot just the active/focused window.")
def screenshot_window() -> ToolResult:
    try:
        import win32gui
    except ImportError:
        return ToolResult(False, "pywin32 isn't available, so I can't target a specific window.")

    hwnd = win32gui.GetForegroundWindow()
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    img = pyautogui.screenshot(region=(left, top, right - left, bottom - top))
    path = _save(img)
    return ToolResult(True, f"Captured the active window: {path.split(chr(92))[-1]}.", data={"path": path}, speech="Captured that window.")


@action(
    "screenshot",
    "region",
    "Screenshot a specific region.",
    required_args=["x", "y", "width", "height"],
)
def screenshot_region(x: int, y: int, width: int, height: int) -> ToolResult:
    img = pyautogui.screenshot(region=(int(x), int(y), int(width), int(height)))
    path = _save(img)
    return ToolResult(True, f"Captured that region: {path.split(chr(92))[-1]}.", data={"path": path}, speech="Captured that region.")


@action("screenshot", "copy_to_clipboard", "Take a screenshot and copy it to the clipboard (no file saved).")
def screenshot_to_clipboard() -> ToolResult:
    try:
        import win32clipboard
    except ImportError:
        return ToolResult(False, "pywin32 isn't available, so I can't copy directly to the clipboard.")

    img = pyautogui.screenshot()
    output = BytesIO()
    img.convert("RGB").save(output, "BMP")
    data = output.getvalue()[14:]  # strip BMP file header, DIB expects the rest
    output.close()

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
    finally:
        win32clipboard.CloseClipboard()

    return ToolResult(True, "Copied a screenshot to your clipboard.")
