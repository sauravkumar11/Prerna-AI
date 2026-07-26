"""
Volume tool
===========
Uses the Windows multimedia virtual keys via keybd_event - no extra
dependency beyond the standard library's ctypes.
"""

from __future__ import annotations

import ctypes
import time

from agent.registry import ToolResult, action

TOOL_DESCRIPTION = "Increase, decrease, mute, or unmute the system volume."

VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
KEYEVENTF_KEYUP = 0x0002


def _press(vk_code: int, times: int = 1) -> None:
    for _ in range(times):
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.05)


@action("volume", "up", "Increase the volume.", tool_description=TOOL_DESCRIPTION)
def volume_up(steps: int = 5) -> ToolResult:
    _press(VK_VOLUME_UP, int(steps) if steps else 5)
    return ToolResult(True, "Turned the volume up.")


@action("volume", "down", "Decrease the volume.")
def volume_down(steps: int = 5) -> ToolResult:
    _press(VK_VOLUME_DOWN, int(steps) if steps else 5)
    return ToolResult(True, "Turned the volume down.")


@action("volume", "mute", "Mute the volume.")
def mute() -> ToolResult:
    _press(VK_VOLUME_MUTE)
    return ToolResult(True, "Muted.")


@action("volume", "unmute", "Unmute the volume (toggles mute again).")
def unmute() -> ToolResult:
    _press(VK_VOLUME_MUTE)
    return ToolResult(True, "Unmuted.")
