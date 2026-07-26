"""
Notepad tool
============
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from agent.registry import ToolResult, action

TOOL_DESCRIPTION = "Open Notepad, or write dictated text straight into a Notepad file."

_NOTES_DIR = Path.home() / "Documents" / "Prerna Notes"


@action("notepad", "open", "Open a blank Notepad window.", tool_description=TOOL_DESCRIPTION)
def open_notepad() -> ToolResult:
    subprocess.Popen("notepad", shell=True)
    return ToolResult(True, "Opening Notepad.")


@action("notepad", "write", "Write dictated text to a new note and open it in Notepad.", required_args=["text"])
def write_text(text: str, filename: str = "") -> ToolResult:
    _NOTES_DIR.mkdir(parents=True, exist_ok=True)
    name = filename.strip() or datetime.now().strftime("note_%Y%m%d_%H%M%S")
    if not name.endswith(".txt"):
        name += ".txt"
    path = _NOTES_DIR / name

    path.write_text(text, encoding="utf-8")
    subprocess.Popen(["notepad", str(path)])

    return ToolResult(True, f"Saved and opened your note: {name}", data={"path": str(path)})


@action("notepad", "append", "Append dictated text to an existing note.", required_args=["filename", "text"])
def append_text(filename: str, text: str) -> ToolResult:
    name = filename.strip()
    if not name.endswith(".txt"):
        name += ".txt"
    path = _NOTES_DIR / name

    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n{text}")

    return ToolResult(True, f"Added to {name}.")
