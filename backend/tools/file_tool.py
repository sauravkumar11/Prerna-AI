"""
File system tool
=================
Basic, guarded filesystem operations. Deletion is marked dangerous and
requires confirmation before it runs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from agent.registry import ToolResult, action
from config.settings import FOLDER_SHORTCUTS as _SHORTCUTS
from config.settings import SCREENSHOT_DIR, CAMERA_CAPTURE_DIR

TOOL_DESCRIPTION = "Create, open, write to, or delete files and folders; jump to common folders."

# Folders to search, in order, when a bare filename (no directory given)
# doesn't exist where naively resolved. This is what actually fixes "open
# the screenshot/photo I just took" — the planner/LLM often only has the
# filename mentioned in a previous reply (by design — full paths aren't
# read aloud/shown), not the app's real save directory, so a bare filename
# resolved against the backend's working directory fails with WinError 2.
_SEARCH_DIRS = [
    SCREENSHOT_DIR,
    CAMERA_CAPTURE_DIR,
    Path.home() / "Pictures" / "Camera Roll",
    Path.home() / "Pictures",
    Path.home() / "Downloads",
    Path.home() / "Documents",
    Path.home() / "Desktop",
]


def _safe_path(path: str) -> Path:
    """Resolve a path and make sure it isn't something obviously dangerous
    like the root of a drive - a lightweight guardrail, not a sandbox."""
    resolved = Path(path).expanduser().resolve()
    if resolved.parent == resolved:  # e.g. "C:\\" itself
        raise ValueError(f"Refusing to operate on a drive root: {resolved}")
    return resolved


def _resolve_existing(path: str) -> Path:
    """Resolve a path for *opening* an existing file/folder.

    If the naive resolution doesn't exist, search common save/output
    folders for a file with the same NAME before giving up — this covers
    both a bare filename (e.g. "screenshot_123.png") and a planner-guessed
    multi-segment path that doesn't actually exist (e.g. it once passed
    literal "Pictures\\Camera Roll" as a path when it only had a folder
    name to go on, not a real filename). Read-only lookup, so a broader
    search here carries no real risk — worst case it fails the same way
    the naive resolution already would have.
    """
    target = _safe_path(path)
    if target.exists():
        return target

    name = Path(path).name
    if not name:
        return target

    for directory in _SEARCH_DIRS:
        candidate = directory / name
        if candidate.exists():
            return candidate
    return target


@action("file", "create", "Create a new file with optional content.", required_args=["path"], tool_description=TOOL_DESCRIPTION)
def create_file(path: str, content: str = "") -> ToolResult:
    target = _safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return ToolResult(True, f"Created file: {target}", speech=f"Created {target.name}.")


@action("file", "append", "Append text to an existing (or new) file.", required_args=["path", "content"])
def append_file(path: str, content: str) -> ToolResult:
    target = _safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as f:
        f.write(content)
    return ToolResult(True, f"Added to {target}", speech=f"Added that to {target.name}.")


@action("file", "open", "Open a file or folder with its default app.", required_args=["path"])
def open_file(path: str) -> ToolResult:
    target = _resolve_existing(path)
    if not target.exists():
        return ToolResult(
            False,
            f"I couldn't find '{path}' in its usual folder or anywhere I checked "
            "(screenshots, captures, Pictures, Downloads, Documents, Desktop).",
        )
    os.startfile(target)  # noqa: S606 - Windows-only by design
    return ToolResult(True, f"Opening {target}", speech="Opening it now.")


@action("file", "create_folder", "Create a new folder.", required_args=["path"])
def create_folder(path: str) -> ToolResult:
    target = _safe_path(path)
    target.mkdir(parents=True, exist_ok=True)
    return ToolResult(True, f"Created folder: {target}", speech=f"Created the {target.name} folder.")


@action("file", "delete", "Delete a file or folder.", required_args=["path"], dangerous=True)
def delete_path(path: str) -> ToolResult:
    target = _safe_path(path)
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink(missing_ok=True)
    return ToolResult(True, f"Deleted {target}", speech=f"Deleted {target.name}.")


@action("file", "open_shortcut", "Open a common folder (downloads, documents, desktop).", required_args=["name"])
def open_shortcut(name: str) -> ToolResult:
    key = name.strip().lower()
    if key not in _SHORTCUTS:
        return ToolResult(False, f"I don't have a shortcut for '{name}'.")
    folder = _SHORTCUTS[key]
    subprocess.Popen(["explorer", str(folder)])
    return ToolResult(True, f"Opening {key.title()}.")


@action("file", "rename", "Rename a file or folder.", required_args=["path", "new_name"])
def rename_path(path: str, new_name: str) -> ToolResult:
    target = _safe_path(path)
    destination = target.parent / new_name
    target.rename(destination)
    return ToolResult(True, f"Renamed to {destination.name}.")


@action("file", "move", "Move a file or folder to a new location.", required_args=["path", "destination"])
def move_path(path: str, destination: str) -> ToolResult:
    target = _safe_path(path)
    dest = _safe_path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(target), str(dest))
    return ToolResult(True, f"Moved to {dest}.", speech=f"Moved it to {dest.name}.")


@action("file", "copy", "Copy a file or folder to a new location.", required_args=["path", "destination"])
def copy_path(path: str, destination: str) -> ToolResult:
    target = _safe_path(path)
    dest = _safe_path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if target.is_dir():
        shutil.copytree(target, dest, dirs_exist_ok=True)
    else:
        shutil.copy2(target, dest)
    return ToolResult(True, f"Copied to {dest}.", speech=f"Copied it to {dest.name}.")


@action("file", "search", "Search for files/folders by name under a folder.", required_args=["query", "path"])
def search_files(query: str, path: str) -> ToolResult:
    root = _safe_path(path)
    if not root.exists():
        return ToolResult(False, f"{root} doesn't exist.")

    matches = [str(p) for p in root.rglob(f"*{query}*")][:25]
    if not matches:
        return ToolResult(True, f"No files matching '{query}' found in {root}.")
    return ToolResult(True, f"Found {len(matches)} match(es).", data={"matches": matches})


@action("file", "zip", "Zip a folder.", required_args=["path"])
def zip_folder(path: str) -> ToolResult:
    target = _safe_path(path)
    archive = shutil.make_archive(str(target), "zip", root_dir=target)
    return ToolResult(True, f"Zipped to {archive}.", speech="Zipped it up.")


@action("file", "extract", "Extract a zip archive.", required_args=["path"])
def extract_zip(path: str, destination: str = "") -> ToolResult:
    target = _safe_path(path)
    dest = _safe_path(destination) if destination else target.parent / target.stem
    shutil.unpack_archive(str(target), str(dest))
    return ToolResult(True, f"Extracted to {dest}.", speech="Extracted it.")
