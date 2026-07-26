"""
Context
=======
Thin layer on top of memory.memory_manager.get_context() that shapes memory
into what a prompt actually needs (contacts as plain dict for the planner,
a short recent-conversation snippet for the persona prompt, etc.).

Deliberately not a separate storage system - `memory/memory_manager.py`
already owns persistence. This module is just the "what does the prompt
need right now" view over it, kept in agent/ since it's agent-facing.
"""

from __future__ import annotations

from typing import Any, Dict, List

from memory.memory_manager import get_context as _get_memory_context
from memory import mood_state as _mood_state
from agent.session import get_session_state


def _get_active_window() -> Dict[str, Any]:
    """Best-effort snapshot of what's currently on screen. Isolated in its
    own try/except so a missing pywin32/psutil install (or no foreground
    window at all) never breaks context building for the rest of the app —
    it just means the planner won't have this piece of context."""
    try:
        from tools.window_tool import get_active_window_info
        return get_active_window_info() or {}
    except Exception:
        return {}


def get_planner_context() -> Dict[str, Any]:
    """What the planner needs: contacts for entity resolution, a snapshot of
    the currently focused window, and Prerna's own session state (current
    app/song/chat/task) so follow-ups like "pause it" or "reply okay to her"
    resolve against structured state instead of re-parsing recent prose."""
    ctx = _get_memory_context()
    return {
        "contacts": ctx.get("contacts", {}),
        "active_window": _get_active_window(),
        "session": get_session_state(),
    }


def get_persona_context(max_turns: int = 6) -> Dict[str, Any]:
    """What the chat/persona prompt needs: profile, habits, recent mood,
    and a short slice of recent conversation for continuity."""
    ctx = _get_memory_context()
    recent_turns: List[Dict[str, Any]] = ctx.get("short_term", [])[-max_turns:]

    mood = _mood_state.get_mood()

    return {
        "profile": ctx.get("profile", {}),
        "habits": ctx.get("habits", []),
        "preferences": ctx.get("preferences", {}),
        "last_emotion": ctx.get("last_emotion", "CALM"),
        "recent_turns": recent_turns,
        "recent_actions": ctx.get("recent_actions", []),
        "mood_description": _mood_state.describe_mood(mood),
        "open_events": _mood_state.get_open_events(),
    }