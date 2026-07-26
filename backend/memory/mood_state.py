"""
Mood State
==========
Persistent, decaying emotional context — the functional difference between
"she picked a mood-tag for this one reply" and "she's actually been in a
mood, and she remembers why."

IMPORTANT / honesty note: this does not give Prerna subjective feelings.
It's a state machine that makes her *responses* consistently track context
over time instead of resetting blank every turn — the same kind of thing a
good customer-support rep or friend does by remembering how a conversation
has been going, not evidence of inner experience. Nothing in this module
should be used to have her claim "I feel X" as a fact about herself; it
should only shape tone, warmth, and what she chooses to bring up.

State tracked:
  - valence   (-1..1)  how the conversation has generally been going
  - energy    (-1..1)  low = tired/subdued, high = excited/animated
  - closeness ( 0..1)  slowly-built familiarity; rises with consistent
                        positive interaction, never swings hard on one turn
  - last_interaction_ts

All three decay toward neutral over time (an emotional beat from a rough
conversation three days ago shouldn't still be coloring tone today), while
`closeness` decays far slower than valence/energy — trust built over many
conversations shouldn't evaporate just because a day passed.

Notable events (interview, exam, illness, a big win, something he's
stressed about) are stored separately with a timestamp and a `resolved`
flag, so she can naturally follow up ("how'd the interview go?") without
needing to be told to remember it, and stop bringing it up once it's
resolved or too old.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List, Optional

from config.settings import MEMORY_DIR
from utils.logger import get_logger

logger = get_logger(__name__)

MOOD_FILE = MEMORY_DIR / "mood_state.json"
_lock = threading.Lock()

# Decay half-lives, in hours — how long until a deviation from neutral has
# roughly halved. Tuned so a single bad exchange doesn't linger for days,
# but closeness (trust) is sticky.
_VALENCE_HALF_LIFE_H = 6.0
_ENERGY_HALF_LIFE_H = 4.0
_CLOSENESS_HALF_LIFE_H = 24.0 * 14  # ~2 weeks to meaningfully fade

_MAX_EVENTS = 25
_EVENT_STALE_DAYS = 10  # stop surfacing an unresolved event after this long

# Rough per-tag nudge applied to (valence, energy) when Prerna uses a given
# emotion tag in a reply — small, so it takes a consistent pattern across a
# conversation to actually shift her mood, not one message.
_TAG_DELTAS: Dict[str, tuple[float, float]] = {
    "EXCITED":   (0.15, 0.20),
    "PLAYFUL":   (0.10, 0.10),
    "CARING":    (0.05, -0.02),
    "SAD":       (-0.15, -0.15),
    "ANGRY":     (-0.10, 0.10),
    "SHY":       (0.02, -0.05),
    "SURPRISED": (0.05, 0.15),
    "CALM":      (0.0, -0.05),
}

_DEFAULT_STATE: Dict[str, Any] = {
    "valence": 0.0,
    "energy": 0.0,
    "closeness": 0.1,
    "last_interaction_ts": None,
    "events": [],  # [{"text": str, "created_ts": float, "resolved": bool}]
}


def _load() -> Dict[str, Any]:
    try:
        with open(MOOD_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Backward/forward compatible — fill in any missing keys.
        merged = {**_DEFAULT_STATE, **data}
        merged["events"] = data.get("events", [])
        return merged
    except Exception:
        return dict(_DEFAULT_STATE)


def _save(state: Dict[str, Any]) -> None:
    with _lock:
        with open(MOOD_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)


def _decay_value(value: float, hours_elapsed: float, half_life_h: float, floor: float = 0.0) -> float:
    """Exponential decay of `value` toward `floor` over `hours_elapsed`."""
    if hours_elapsed <= 0 or half_life_h <= 0:
        return value
    decay_factor = 0.5 ** (hours_elapsed / half_life_h)
    return floor + (value - floor) * decay_factor


def _apply_decay(state: Dict[str, Any]) -> Dict[str, Any]:
    now = time.time()
    last_ts = state.get("last_interaction_ts")
    if last_ts:
        hours = (now - last_ts) / 3600.0
        state["valence"] = round(_decay_value(state["valence"], hours, _VALENCE_HALF_LIFE_H), 4)
        state["energy"] = round(_decay_value(state["energy"], hours, _ENERGY_HALF_LIFE_H), 4)
        state["closeness"] = round(
            _decay_value(state["closeness"], hours, _CLOSENESS_HALF_LIFE_H, floor=0.05), 4
        )
    return state


def get_mood() -> Dict[str, Any]:
    """Current mood, with time-decay already applied. Safe to call often —
    decay is computed on read, not on a background timer."""
    state = _load()
    return _apply_decay(state)


def update_from_tag(tag: str, closeness_bump: float = 0.01) -> Dict[str, Any]:
    """Nudge mood after Prerna's reply used a given emotion tag. Small,
    bounded moves — a real mood shift takes a pattern of turns, not one."""
    state = _apply_decay(_load())

    dv, de = _TAG_DELTAS.get((tag or "").upper(), (0.0, 0.0))
    state["valence"] = max(-1.0, min(1.0, state["valence"] + dv))
    state["energy"] = max(-1.0, min(1.0, state["energy"] + de))
    state["closeness"] = max(0.0, min(1.0, state["closeness"] + closeness_bump))
    state["last_interaction_ts"] = time.time()

    _save(state)
    return state


def remember_event(text: str) -> None:
    """Record a notable emotional event (interview, exam, illness, a win —
    anything worth naturally following up on later)."""
    if not text or not text.strip():
        return
    state = _load()
    events: List[Dict[str, Any]] = state.get("events", [])
    events.append({"text": text.strip(), "created_ts": time.time(), "resolved": False})
    state["events"] = events[-_MAX_EVENTS:]
    _save(state)
    logger.info("Mood: remembered event — %s", text.strip())


def resolve_event(index_or_text: Any) -> None:
    """Mark an event resolved so it stops surfacing as a follow-up."""
    state = _load()
    events = state.get("events", [])

    if isinstance(index_or_text, int):
        if 0 <= index_or_text < len(events):
            events[index_or_text]["resolved"] = True
    else:
        for ev in events:
            if ev.get("text") == index_or_text:
                ev["resolved"] = True

    state["events"] = events
    _save(state)


def get_open_events(max_items: int = 3) -> List[str]:
    """Unresolved, not-too-stale events — candidates for a natural
    follow-up ("how'd the interview go?"). Most recent first."""
    state = _load()
    now = time.time()
    cutoff = now - (_EVENT_STALE_DAYS * 86400)
    open_events = [
        ev["text"] for ev in reversed(state.get("events", []))
        if not ev.get("resolved") and ev.get("created_ts", 0) >= cutoff
    ]
    return open_events[:max_items]


def describe_mood(state: Optional[Dict[str, Any]] = None) -> str:
    """Short natural-language mood summary for the prompt — not for
    display to the user, just context for the model."""
    state = state or get_mood()
    v, e, c = state["valence"], state["energy"], state["closeness"]

    if v > 0.3:
        tone = "warm and upbeat"
    elif v < -0.3:
        tone = "a little heavy, gentler than usual"
    else:
        tone = "even-keeled"

    if e > 0.3:
        energy_desc = "high energy"
    elif e < -0.3:
        energy_desc = "low energy, subdued"
    else:
        energy_desc = "normal energy"

    closeness_desc = "still getting to know him" if c < 0.25 else (
        "comfortably familiar" if c < 0.6 else "very close, long-standing rapport"
    )

    return f"{tone}, {energy_desc}; {closeness_desc} (valence={v:+.2f}, energy={e:+.2f}, closeness={c:.2f})"