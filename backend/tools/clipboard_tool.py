"""
Clipboard tool
==============
"""

from __future__ import annotations

import pyperclip

from agent.registry import ToolResult, action

TOOL_DESCRIPTION = "Read, write, or clear the system clipboard."


@action("clipboard", "copy", "Copy text to the clipboard.", required_args=["text"], tool_description=TOOL_DESCRIPTION)
def copy(text: str) -> ToolResult:
    pyperclip.copy(text)
    return ToolResult(True, "Copied to clipboard.")


@action("clipboard", "read", "Read the current clipboard contents.")
def read() -> ToolResult:
    content = pyperclip.paste()
    if not content:
        return ToolResult(True, "Your clipboard is empty.", data={"content": ""})
    preview = content if len(content) <= 200 else content[:200] + "..."
    return ToolResult(True, f"Clipboard has: {preview}", data={"content": content})


@action("clipboard", "clear", "Clear the clipboard.")
def clear() -> ToolResult:
    pyperclip.copy("")
    return ToolResult(True, "Cleared the clipboard.")
