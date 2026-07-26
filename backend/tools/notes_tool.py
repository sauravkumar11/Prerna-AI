"""
Notes tool
==========
Structured notes Prerna can search/recall, stored alongside the rest of
memory. Different from notepad_tool, which writes visible .txt files you
open and edit yourself.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List

from agent.registry import ToolResult, action

TOOL_DESCRIPTION = "Create, append to, and search short notes Prerna remembers."

from config.settings import NOTES_FILE as _NOTES_FILE


def _load() -> List[Dict[str, Any]]:
    try:
        with open(_NOTES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(notes: List[Dict[str, Any]]) -> None:
    with open(_NOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(notes, f, indent=2, ensure_ascii=False)


@action("notes", "create", "Create a new note.", required_args=["content"], tool_description=TOOL_DESCRIPTION)
def create_note(content: str, title: str = "") -> ToolResult:
    notes = _load()
    note = {
        "id": len(notes) + 1,
        "title": title or content[:40],
        "content": content,
        "created": datetime.now().isoformat(),
    }
    notes.append(note)
    _save(notes)
    return ToolResult(True, f"Noted: {note['title']}")


@action("notes", "append", "Append to the most recent note, or one matching a title.", required_args=["content"])
def append_note(content: str, title: str = "") -> ToolResult:
    notes = _load()
    if not notes:
        return create_note(content, title)

    target = None
    if title:
        for n in reversed(notes):
            if title.lower() in n["title"].lower():
                target = n
                break
    if target is None:
        target = notes[-1]

    target["content"] += f"\n{content}"
    _save(notes)
    return ToolResult(True, f"Added to note: {target['title']}")


@action("notes", "search", "Search notes by keyword.", required_args=["query"])
def search_notes(query: str) -> ToolResult:
    notes = _load()
    matches = [n for n in notes if query.lower() in n["content"].lower() or query.lower() in n["title"].lower()]
    if not matches:
        return ToolResult(True, f"No notes found matching '{query}'.")
    preview = "; ".join(n["title"] for n in matches[:5])
    return ToolResult(True, f"Found {len(matches)} note(s): {preview}", data={"matches": matches})
