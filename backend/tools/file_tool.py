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
from typing import List, Optional

from agent.registry import ToolResult, action
from config.settings import FOLDER_SHORTCUTS as _SHORTCUTS
from config.settings import SCREENSHOT_DIR, CAMERA_CAPTURE_DIR
from utils.windows_folders import get_special_folder, is_special_folder_name

TOOL_DESCRIPTION = "Create, open, write to, or delete files and folders; jump to common folders."


def _search_dirs() -> List[Path]:
    """Folders to search, in order, when a bare filename (no directory given)
    doesn't exist where naively resolved. This is what actually fixes "open
    the screenshot/photo I just took" — the planner/LLM often only has the
    filename mentioned in a previous reply (by design — full paths aren't
    read aloud/shown), not the app's real save directory, so a bare filename
    resolved against the backend's working directory fails with WinError 2.

    Built lazily (not as a module-level constant) so the real Win32-resolved
    special-folder paths (which can depend on OneDrive redirection) are used
    rather than a value baked in at import time.
    """
    pictures = get_special_folder("pictures") or (Path.home() / "Pictures")
    downloads = get_special_folder("downloads") or (Path.home() / "Downloads")
    documents = get_special_folder("documents") or (Path.home() / "Documents")
    desktop = get_special_folder("desktop") or (Path.home() / "Desktop")
    return [
        SCREENSHOT_DIR,
        CAMERA_CAPTURE_DIR,
        pictures / "Camera Roll",
        pictures,
        downloads,
        documents,
        desktop,
    ]


def _resolve_with_special_folders(path: str) -> Optional[Path]:
    """
    v1.2.1 Bug 1 fix. If `path`'s first segment is a recognized Windows
    special-folder name or alias (e.g. "Desktop", "downloads"), resolve
    that segment via the real Win32 API (utils.windows_folders) and join
    whatever remains of the path onto it.

    Returns None if the first segment isn't a recognized special folder —
    callers fall through to ordinary path resolution in that case, so any
    path not starting with a special-folder name/alias is completely
    unaffected by this function existing.
    """
    raw = Path(path.strip())
    parts = raw.parts
    if not parts:
        return None

    first = parts[0]
    if not is_special_folder_name(first):
        return None

    base = get_special_folder(first)
    if base is None:
        return None

    remainder = parts[1:]
    return base.joinpath(*remainder) if remainder else base


def _safe_path(path: str) -> Path:
    """Resolve a path and make sure it isn't something obviously dangerous
    like the root of a drive - a lightweight guardrail, not a sandbox.

    Before v1.2.1 this did a plain Path(path).expanduser().resolve(), which
    resolved relative paths against the backend process's working
    directory - so "Desktop/saurav" created backend/Desktop/saurav instead
    of the real Windows Desktop. Now, if the path's first segment names a
    special folder, it's resolved via the real Win32 API first; every other
    path resolves exactly as before.
    """
    special = _resolve_with_special_folders(path)
    resolved = special.resolve() if special is not None else Path(path).expanduser().resolve()
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

    for directory in _search_dirs():
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

    # Prefer the real Win32-resolved special folder when the name matches
    # one (correctly handles OneDrive redirection); fall back to the
    # config-defined shortcuts dict for anything else it already covers.
    special = get_special_folder(key)
    if special is not None:
        folder = special
    elif key in _SHORTCUTS:
        folder = _SHORTCUTS[key]
    else:
        return ToolResult(False, f"I don't have a shortcut for '{name}'.")

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