"""
VS Code tool
============
Requires the `code` CLI to be on PATH (VS Code's "Add to PATH" install option).
"""

from __future__ import annotations

import subprocess

from agent.registry import ToolResult, action
from agent.verification import process_running

TOOL_DESCRIPTION = "Open VS Code, optionally to a specific project folder."


@action(
    "vscode", "open", "Open VS Code.", tool_description=TOOL_DESCRIPTION,
    verify=process_running("code.exe", "code - insiders.exe"), max_retries=1,
)
def open_editor() -> ToolResult:
    subprocess.Popen("code", shell=True)
    return ToolResult(True, "Opening VS Code.")


@action("vscode", "open_path", "Open VS Code to a specific folder or file.", required_args=["path"])
def open_path(path: str) -> ToolResult:
    subprocess.Popen(["code", path], shell=True)
    return ToolResult(True, f"Opening {path} in VS Code.")
