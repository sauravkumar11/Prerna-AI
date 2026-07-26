"""
Predictor
=========
Proactive suggestions based on what Saurav just said, the time of day,
recent activity, and conversation context.

Was an `elif` chain — only the first matching category could ever fire, so
"I'm hungry and kinda bored" only ever triggered the hungry branch. Rewritten
so every category is checked independently and scored, then the best one
wins. Still returns at most one suggestion (voice UX shouldn't stack asks),
but now the *right* one wins instead of whichever branch happened to be
first in the file.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, NamedTuple, Optional

from memory.memory_manager import get_recent_actions
from utils.logger import get_logger

logger = get_logger(__name__)


class Trigger(NamedTuple):
    name: str
    keywords: List[str]
    build: Any  # (recent: List[str], hour: int) -> Optional[str]
    weight: int = 1  # higher wins on tie / overlap


def _recent_action_names(n: int = 10) -> List[str]:
    return [a.get("action", "") for a in get_recent_actions(n)]


def _sleep_suggestion(recent: List[str], hour: int) -> Optional[str]:
    parts = []
    if "system.shutdown" not in recent and "system.sleep" not in recent:
        parts.append("shut down the laptop")
    if "alarm.set" not in recent:
        parts.append("set your morning alarm")
    return f"Should I {' and '.join(parts)}?" if parts else None


def _leaving_suggestion(recent: List[str], hour: int) -> Optional[str]:
    parts = []
    if "search.maps" not in recent:
        parts.append("open Maps")
    if "whatsapp.send_message" not in recent:
        parts.append("message someone?")
    return ("Should I " + " or ".join(parts) + "?") if parts else None


def _work_suggestion(recent: List[str], hour: int) -> Optional[str]:
    unopened = []
    if "browser.open_site" not in recent:
        unopened.append("Outlook")
    if "whatsapp.open" not in recent:
        unopened.append("WhatsApp")
    return f"Should I open {' and '.join(unopened)} for you?" if unopened else None


def _gym_suggestion(recent: List[str], hour: int) -> Optional[str]:
    if "browser.open_site" not in recent:
        return "Should I open Spotify for your workout playlist?"
    return None


def _coding_suggestion(recent: List[str], hour: int) -> Optional[str]:
    unopened = []
    if "vscode.open" not in recent:
        unopened.append("VS Code")
    if "browser.open_site" not in recent:
        unopened.append("Chrome")
    return f"Should I open {' and '.join(unopened)}?" if unopened else None


def _bored_suggestion(recent: List[str], hour: int) -> Optional[str]:
    if 18 <= hour <= 23:
        return "Should I open YouTube or play some music?"
    return "Should I open YouTube?"


def _hungry_suggestion(recent: List[str], hour: int) -> Optional[str]:
    if "search.restaurants" not in recent:
        return "Should I search for restaurants nearby?"
    return None


def _stressed_suggestion(recent: List[str], hour: int) -> Optional[str]:
    return "Should I play some calming music?"


# Order doesn't matter anymore — every trigger is checked, best-scoring wins.
TRIGGERS: List[Trigger] = [
    Trigger(
        "sleep",
        ["sone", "so ja", "good night", "neend", "sleep", "sulana", "so gaya", "so rha"],
        _sleep_suggestion,
        weight=3,  # a clear end-of-day signal should usually beat weaker ones
    ),
    Trigger(
        "leaving",
        ["ja raha", "ja rhi", "leaving", "nikal", "going out", "bahar ja", "niklu"],
        _leaving_suggestion,
        weight=2,
    ),
    Trigger(
        "stressed",
        ["stressed", "tired", "thaka", "thak gaya", "pareshaan", "tension", "anxious", "overwhelmed"],
        _stressed_suggestion,
        weight=2,
    ),
    Trigger(
        "work",
        ["office", "work", "meeting", "kaam", "job", "deadline"],
        _work_suggestion,
    ),
    Trigger(
        "coding",
        ["coding", "code", "programming", "vs code", "project", "github", "bug", "error"],
        _coding_suggestion,
    ),
    Trigger(
        "gym",
        ["gym", "workout", "exercise", "running", "jogging", "warmup"],
        _gym_suggestion,
    ),
    Trigger(
        "hungry",
        ["hungry", "bhookh", "khana", "food", "kha lu", "eat", "bhukh"],
        _hungry_suggestion,
    ),
    Trigger(
        "bored",
        ["bored", "free", "timepass", "kuch nahi", "boring", "khaali"],
        _bored_suggestion,
    ),
]


def predict(user_message: str, memory: Dict[str, Any]) -> List[str]:
    msg = user_message.lower()
    hour = datetime.now().hour
    recent = _recent_action_names()

    best_text: Optional[str] = None
    best_score = -1

    for trigger in TRIGGERS:
        hits = sum(1 for kw in trigger.keywords if kw in msg)
        if not hits:
            # gym also fires on early-morning hour alone, matching old behavior
            if trigger.name == "gym" and hour == 5:
                hits = 1
            else:
                continue

        text = trigger.build(recent, hour)
        if not text:
            continue

        score = hits * trigger.weight
        if score > best_score:
            best_score = score
            best_text = text
            logger.debug("Prediction candidate: %s (score=%d) -> %s", trigger.name, score, text)

    return [best_text] if best_text else []