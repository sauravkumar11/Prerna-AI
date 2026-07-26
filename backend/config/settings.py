"""
Settings
========
Single source of truth for every configurable value: environment variables,
paths, model names, CORS origins, feature flags.

Import from here instead of calling os.getenv() in any other file.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Resolve and load .env from the backend root, regardless of where the
# process was started from.
_BACKEND_DIR = Path(__file__).parent.parent
load_dotenv(dotenv_path=_BACKEND_DIR / ".env")

# ── API keys ──────────────────────────────────────────────────────────────────
# Collect every GEMINI_API_KEY* from .env regardless of ordering.
# Supports: GEMINI_API_KEY, GEMINI_API_KEY_2, GEMINI_API_KEY_3 ... _7
_all_key_candidates = [
    os.getenv("GEMINI_API_KEY", ""),
    os.getenv("GEMINI_API_KEY_2", ""),
    os.getenv("GEMINI_API_KEY_3", ""),
    os.getenv("GEMINI_API_KEY_4", ""),
    os.getenv("GEMINI_API_KEY_5", ""),
    os.getenv("GEMINI_API_KEY_6", ""),
    os.getenv("GEMINI_API_KEY_7", ""),
]

# Filter empty, deduplicate, preserve order
_seen: set = set()
GEMINI_API_KEYS: list[str] = []
for _k in _all_key_candidates:
    if _k and _k not in _seen:
        _seen.add(_k)
        GEMINI_API_KEYS.append(_k)

# Expose primary key for any legacy code that imports GEMINI_API_KEY directly
GEMINI_API_KEY: str = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""

if not GEMINI_API_KEYS:
    raise ValueError("No GEMINI_API_KEY found in .env — please add one.")

# ── Model ─────────────────────────────────────────────────────────────────────
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_CHAT_TEMPERATURE: float = float(os.getenv("GEMINI_CHAT_TEMPERATURE", "0.65"))
GEMINI_PLAN_TEMPERATURE: float = float(os.getenv("GEMINI_PLAN_TEMPERATURE", "0.0"))

# ── Server ────────────────────────────────────────────────────────────────────
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))
RELOAD: bool = os.getenv("RELOAD", "true").lower() == "true"

CORS_ORIGINS: list[str] = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]

# ── Storage paths ─────────────────────────────────────────────────────────────
BACKEND_DIR: Path = _BACKEND_DIR
MEMORY_DIR: Path = BACKEND_DIR / "memory"
SCREENSHOT_DIR: Path = BACKEND_DIR / "screenshots"
CAMERA_CAPTURE_DIR: Path = BACKEND_DIR / "captures"
NOTES_FILE: Path = MEMORY_DIR / "notes.json"
NOTEPAD_NOTES_DIR: Path = Path.home() / "Documents" / "Prerna Notes"

# ── Common Windows folder shortcuts ───────────────────────────────────────────
FOLDER_SHORTCUTS: dict[str, Path] = {
    "downloads": Path.home() / "Downloads",
    "documents": Path.home() / "Documents",
    "desktop": Path.home() / "Desktop",
}

# ── Browser executables ───────────────────────────────────────────────────────
BROWSER_EXES: dict[str, str] = {
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "brave": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
}

# ── Windows app launch commands (used with shell=True) ───────────────────────
WINDOWS_APPS: dict[str, str] = {
    "calculator": "calc",
    "paint": "mspaint",
    "cmd": "cmd",
    "powershell": "powershell",
    "terminal": "wt",
    "explorer": "explorer",
    "control panel": "control",
    "settings": "start ms-settings:",
    "task manager": "taskmgr",
    "device manager": "devmgmt.msc",
    "snipping tool": "snippingtool",
    "sticky notes": "start ms-stickynotes:",
    "clock": "start ms-clock:",
    "alarms": "start ms-clock:",
    "store": "start ms-windows-store:",
    "notepad": "notepad",
}

# ── Memory limits ─────────────────────────────────────────────────────────────
MAX_CONVERSATION_TURNS: int = 200
MAX_ACTIVITY_LOG_ENTRIES: int = 500
MAX_RECENT_TURNS_FOR_PLANNER: int = 6

# ── Task Scheduler prefix (alarm tool) ───────────────────────────────────────
ALARM_TASK_PREFIX: str = "Prerna_Alarm_"