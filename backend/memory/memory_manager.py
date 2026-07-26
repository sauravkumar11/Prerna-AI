"""
Memory Manager
==============
Everything Prerna remembers, split into a few kinds of memory:

- Long-term memory   -> memory.json (profile, contacts, habits, preferences)
- Activity memory    -> activity_log.json (every tool call, success/fail)
- Short-term memory  -> in-process ring buffer of the current session
- Conversation memory-> rolling log of recent chat turns (persisted)
- Emotion memory     -> last emotion tag Prerna used, so tone stays consistent
- Context memory     -> get_context() merges all of the above into one dict
                         for prompt-building, replacing the ad-hoc assembly
                         that used to live in main.py

Everything below is backward compatible: load_memory/save_memory/get_contact/
add_contact/get_profile/get_preferences/get_habits/remember/log_activity all
keep their original signatures and behavior. New functionality is additive.
"""

from __future__ import annotations

import json
import threading
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

from config.settings import (
    MEMORY_DIR,
    MAX_CONVERSATION_TURNS,
    MAX_ACTIVITY_LOG_ENTRIES,
)
from utils.logger import get_logger

logger = get_logger(__name__)

MEMORY_FILE = MEMORY_DIR / "memory.json"
LOG_FILE = MEMORY_DIR / "activity_log.json"
CONVERSATION_FILE = MEMORY_DIR / "conversation_log.json"

_lock = threading.Lock()

# ==========================
# In-process write-through cache for memory.json
# Eliminates repeated disk reads on every get_contact/get_profile call.
# Cache is invalidated whenever save_memory() writes a new value.
# ==========================
_memory_cache: Optional[Dict[str, Any]] = None
_cache_lock = threading.Lock()


def _invalidate_cache() -> None:
    global _memory_cache
    with _cache_lock:
        _memory_cache = None


# ==========================
# Short-term / emotion memory (in-process, resets on backend restart)
# ==========================
_SHORT_TERM: Deque[Dict[str, Any]] = deque(maxlen=20)
_LAST_EMOTION: str = "CALM"


# ==========================
# Long-term memory (memory.json)
# ==========================

def load_memory() -> Dict[str, Any]:
    global _memory_cache
    with _cache_lock:
        if _memory_cache is not None:
            return _memory_cache
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    with _cache_lock:
        _memory_cache = data
    return data


def save_memory(memory: Dict[str, Any]) -> None:
    with _lock:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=4, ensure_ascii=False)
    _invalidate_cache()


def get_contact(name: str) -> str:
    memory = load_memory()
    contacts = memory.get("contacts", {})

    for key, value in contacts.items():
        if key.lower() == name.lower():
            return value

    return name


def add_contact(alias: str, real_name: str) -> None:
    memory = load_memory()
    memory.setdefault("contacts", {})[alias] = real_name
    save_memory(memory)


def remove_contact(alias: str) -> bool:
    memory = load_memory()
    contacts = memory.get("contacts", {})
    for key in list(contacts.keys()):
        if key.lower() == alias.lower():
            del contacts[key]
            save_memory(memory)
            return True
    return False


def get_profile() -> Dict[str, Any]:
    return load_memory().get("profile", {})


def get_preferences() -> Dict[str, Any]:
    return load_memory().get("preferences", {})


def set_preference(key: str, value: Any) -> None:
    memory = load_memory()
    memory.setdefault("preferences", {})[key] = value
    save_memory(memory)


def get_habits() -> Any:
    return load_memory().get("habits", [])


def remember(key: str, value: Any) -> None:
    """Generic long-term memory setter, e.g. remember('projects', [...])."""
    memory = load_memory()
    memory[key] = value
    save_memory(memory)


# ==========================
# Activity memory (activity_log.json)
# ==========================

def log_activity(action: str, success: Optional[bool] = None, details: str = "") -> None:
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            logs = json.load(f)
    except Exception:
        logs = []

    entry: Dict[str, Any] = {
        "action": action,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if success is not None:
        entry["success"] = success
    if details:
        entry["details"] = details

    logs.append(entry)
    logs = logs[-MAX_ACTIVITY_LOG_ENTRIES:]  # keep last N events

    with _lock:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2)


def get_recent_actions(n: int = 10) -> List[Dict[str, Any]]:
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            logs = json.load(f)
    except Exception:
        return []
    return logs[-n:]


# ==========================
# Short-term / conversation memory
# ==========================

def add_short_term(role: str, content: str) -> None:
    """Track a turn in the in-process short-term buffer (survives this run only)."""
    _SHORT_TERM.append({"role": role, "content": content, "time": datetime.now().isoformat()})


def get_short_term() -> List[Dict[str, Any]]:
    return list(_SHORT_TERM)


def add_conversation_turn(role: str, content: str) -> None:
    """Persist a turn to disk so conversation memory survives restarts."""
    add_short_term(role, content)

    try:
        with open(CONVERSATION_FILE, "r", encoding="utf-8") as f:
            turns = json.load(f)
    except Exception:
        turns = []

    turns.append({"role": role, "content": content, "time": datetime.now().isoformat()})
    turns = turns[-MAX_CONVERSATION_TURNS:]  # keep last N turns

    with _lock:
        with open(CONVERSATION_FILE, "w", encoding="utf-8") as f:
            json.dump(turns, f, indent=2, ensure_ascii=False)


def get_conversation_history(n: int = 20) -> List[Dict[str, Any]]:
    try:
        with open(CONVERSATION_FILE, "r", encoding="utf-8") as f:
            turns = json.load(f)
    except Exception:
        return []
    return turns[-n:]


# ==========================
# Emotion memory
# ==========================

def set_last_emotion(emotion: str) -> None:
    global _LAST_EMOTION
    _LAST_EMOTION = emotion


def get_last_emotion() -> str:
    return _LAST_EMOTION


# ==========================
# Context memory - single entry point for prompt building
# ==========================

def get_context() -> Dict[str, Any]:
    """Merge every memory type into one dict, ready to drop into a prompt."""
    memory = load_memory()
    return {
        "profile": memory.get("profile", {}),
        "habits": memory.get("habits", []),
        "preferences": memory.get("preferences", {}),
        "contacts": memory.get("contacts", {}),
        "recent_actions": get_recent_actions(5),
        "last_emotion": get_last_emotion(),
        "short_term": get_short_term(),
    }
