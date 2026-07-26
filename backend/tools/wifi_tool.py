"""
WiFi tool
=========
Uses `netsh` to enable/disable the WiFi adapter. Requires the interface to
be named "Wi-Fi" (Windows default) and may need admin rights; falls back to
opening network settings if the command fails, same pattern as bluetooth_tool.
"""

from __future__ import annotations

import subprocess

from agent.registry import ToolResult, action

TOOL_DESCRIPTION = "Turn WiFi on/off (best effort) or open network settings."

_INTERFACE_NAME = "Wi-Fi"


def _try_netsh(state: str) -> bool:
    try:
        result = subprocess.run(
            ["netsh", "interface", "set", "interface", _INTERFACE_NAME, f"admin={state}"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


@action("wifi", "on", "Turn WiFi on.", tool_description=TOOL_DESCRIPTION)
def wifi_on() -> ToolResult:
    if _try_netsh("enabled"):
        return ToolResult(True, "Turned WiFi on.")
    subprocess.Popen("start ms-settings:network-wifi", shell=True)
    return ToolResult(True, "I couldn't toggle WiFi directly (needs admin rights), so I opened network settings for you.")


@action("wifi", "off", "Turn WiFi off.")
def wifi_off() -> ToolResult:
    if _try_netsh("disabled"):
        return ToolResult(True, "Turned WiFi off.")
    subprocess.Popen("start ms-settings:network-wifi", shell=True)
    return ToolResult(True, "I couldn't toggle WiFi directly (needs admin rights), so I opened network settings for you.")
