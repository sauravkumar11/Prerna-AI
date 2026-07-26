"""
Session State
=============
In-process memory of what Prerna is *currently doing*: which app has her
attention, what song/video is playing, which WhatsApp chat is open, what
folder/document was last touched, and what multi-step task (if any) is in
progress.

This is deliberately NOT persisted to disk like memory.json — it describes
live desktop state (a browser tab, a focused app) that's meaningless after
a backend restart anyway, same reasoning as memory_manager's existing
short-term buffer. It resets when the backend restarts, which is correct:
there's no "current song" to remember if nothing was actually playing when
it restarted.

This is what makes a bare follow-up like "pause it", "next one", "reply
okay to her" resolvable — today those only work if the exact context is
still sitting in the last few conversation turns as text `agent.planner`
has to re-read every time. Session state gives the planner a structured,
always-current answer instead of relying on it re-deriving that from prose.

Updated automatically after a successful tool call via `update_from_action`,
which is called once from `agent.executor` — no other file needs to import
this to benefit; new tools get picked up by adding an updater function
below, same self-contained spirit as the tool registry.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SessionState:
    current_app: Optional[str] = None
    focused_window: Optional[str] = None
    browser_tab: Optional[str] = None
    folder: Optional[str] = None
    document: Optional[str] = None
    song: Optional[str] = None
    whatsapp_chat: Optional[str] = None
    current_task: Optional[str] = None
    pending_tasks: List[str] = field(default_factory=list)
    completed_tasks: List[str] = field(default_factory=list)
    # Explicit "what did I just save" slots — read/written directly by tool
    # actions (screenshot_tool, camera_tool), not inferred from re-reading
    # prior chat text. This is what makes "open that", "open the picture I
    # just took" resolve to a real path instead of the LLM guessing a
    # folder name from a previous reply's wording.
    last_screenshot: Optional[str] = None
    last_photo: Optional[str] = None


_state = SessionState()
_lock = threading.Lock()

# How many completed tasks to keep around for "what did you just do" context.
_MAX_COMPLETED_TASKS = 10


def _set(**fields: Any) -> None:
    with _lock:
        for key, value in fields.items():
            if value is None or value == "":
                continue
            setattr(_state, key, value)


def get_session_state() -> Dict[str, Any]:
    with _lock:
        return {
            "current_app": _state.current_app,
            "focused_window": _state.focused_window,
            "browser_tab": _state.browser_tab,
            "folder": _state.folder,
            "document": _state.document,
            "song": _state.song,
            "whatsapp_chat": _state.whatsapp_chat,
            "current_task": _state.current_task,
            "pending_tasks": list(_state.pending_tasks),
            "completed_tasks": list(_state.completed_tasks[-5:]),
            "last_screenshot": _state.last_screenshot,
            "last_photo": _state.last_photo,
        }


def clear_session() -> None:
    """Reset everything — useful for tests, or a "forget what we were doing" command."""
    global _state
    with _lock:
        _state = SessionState()


# ── Task tracking (whole-plan level, called from execute_plan) ─────────────

def start_task(description: str, step_count: int = 1) -> None:
    if step_count <= 1:
        # Single-step commands aren't really a "task in progress" worth
        # narrating back — only multi-step plans get tracked as a task.
        return
    _set(current_task=description)


def finish_task(description: str, success: bool) -> None:
    with _lock:
        if _state.current_task == description:
            _state.current_task = None
        label = description if success else f"{description} (failed)"
        _state.completed_tasks.append(label)
        _state.completed_tasks = _state.completed_tasks[-_MAX_COMPLETED_TASKS:]


# ── Per-tool updaters (called from update_from_action) ─────────────────────
# Each updater gets (action_name, args, result) for its tool and calls _set()
# with whatever it can confidently extract. Keep these conservative — only
# set a field when there's an actual signal, never guess.

def _update_youtube(action_name: str, args: Dict[str, Any], result: Any) -> None:
    data = getattr(result, "data", None) or {}
    title = data.get("title") or args.get("query")
    if action_name in ("search", "play_first_result") and title:
        _set(current_app="YouTube", song=title)
    elif action_name in ("play_pause", "next", "previous", "skip_ad"):
        _set(current_app="YouTube")


def _update_whatsapp(action_name: str, args: Dict[str, Any], result: Any) -> None:
    contact = args.get("contact")
    if action_name in ("send_message", "voice_call", "video_call", "open_chat") and contact:
        _set(current_app="WhatsApp", whatsapp_chat=contact)
    elif action_name == "open":
        _set(current_app="WhatsApp")


def _update_vscode(action_name: str, args: Dict[str, Any], result: Any) -> None:
    path = args.get("path")
    if path:
        _set(current_app="VS Code", folder=path)
    else:
        _set(current_app="VS Code")


def _update_browser(action_name: str, args: Dict[str, Any], result: Any) -> None:
    tab = args.get("site") or args.get("url") or args.get("query")
    _set(current_app="Browser", browser_tab=tab)


def _update_file(action_name: str, args: Dict[str, Any], result: Any) -> None:
    path = args.get("path")
    if action_name in ("create", "append", "open") and path:
        _set(document=path)


def _update_notepad(action_name: str, args: Dict[str, Any], result: Any) -> None:
    _set(current_app="Notepad")


def _update_camera(action_name: str, args: Dict[str, Any], result: Any) -> None:
    data = getattr(result, "data", None) or {}
    path = data.get("path")  # only take_picture/capture set a confirmed real path
    if path:
        _set(current_app="Camera", last_photo=path)
    else:
        _set(current_app="Camera")


def _update_screenshot(action_name: str, args: Dict[str, Any], result: Any) -> None:
    data = getattr(result, "data", None) or {}
    path = data.get("path")
    if path:
        _set(last_screenshot=path)


def _update_coding(action_name: str, args: Dict[str, Any], result: Any) -> None:
    path = args.get("path")
    if path:
        _set(current_app="VS Code", folder=path)


_UPDATERS: Dict[str, Callable[[str, Dict[str, Any], Any], None]] = {
    "youtube": _update_youtube,
    "whatsapp": _update_whatsapp,
    "vscode": _update_vscode,
    "browser": _update_browser,
    "file": _update_file,
    "notepad": _update_notepad,
    "camera": _update_camera,
    "coding": _update_coding,
    "screenshot": _update_screenshot,
}


def update_from_action(tool_name: str, action_name: str, args: Dict[str, Any], result: Any) -> None:
    """Called once per successful tool step, from agent.executor.

    Silently does nothing for tools with no updater registered above — most
    tools (volume, bluetooth, system, screenshot, ...) don't represent an
    ongoing "thing Prerna is doing" worth tracking as session state, and
    that's fine; this is additive, not a requirement for every tool.
    """
    if not getattr(result, "success", False):
        return
    updater = _UPDATERS.get(tool_name)
    if updater is None:
        return
    try:
        updater(action_name, args, result)
    except Exception:
        logger.debug("Session updater for '%s' failed harmlessly", tool_name, exc_info=True)