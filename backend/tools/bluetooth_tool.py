"""
Bluetooth tool
==============
Windows doesn't expose a simple, no-admin API to silently flip the Bluetooth
radio on/off. The reliable cross-machine approach is to jump straight to the
Bluetooth settings pane so you can toggle it in one click; we also attempt a
PowerShell-based radio toggle for machines where it's supported, and fall
back cleanly if it isn't (never crashes either way).
"""

from __future__ import annotations

import subprocess

from agent.registry import ToolResult, action

TOOL_DESCRIPTION = "Turn Bluetooth on/off (best effort) or open Bluetooth settings."

_POWERSHELL_TOGGLE = (
    "Get-PnpDevice -Class Bluetooth | Where-Object {{$_.Status -eq 'OK'}} | "
    "{verb}-PnpDevice -Confirm:$false"
)


def _try_powershell_toggle(verb: str) -> bool:
    try:
        result = subprocess.run(
            ["powershell", "-Command", _POWERSHELL_TOGGLE.format(verb=verb)],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


@action("bluetooth", "on", "Turn Bluetooth on.", tool_description=TOOL_DESCRIPTION)
def bluetooth_on() -> ToolResult:
    if _try_powershell_toggle("Enable"):
        return ToolResult(True, "Turned Bluetooth on.")
    subprocess.Popen("start ms-settings:bluetooth", shell=True)
    return ToolResult(True, "I couldn't toggle Bluetooth directly (needs admin rights), so I opened Bluetooth settings for you.")


@action("bluetooth", "off", "Turn Bluetooth off.")
def bluetooth_off() -> ToolResult:
    if _try_powershell_toggle("Disable"):
        return ToolResult(True, "Turned Bluetooth off.")
    subprocess.Popen("start ms-settings:bluetooth", shell=True)
    return ToolResult(True, "I couldn't toggle Bluetooth directly (needs admin rights), so I opened Bluetooth settings for you.")
