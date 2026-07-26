"""
Instant Engine (Tier 0)
========================
Zero-LLM, zero-planner, zero-network-round-trip execution for commands
where the mapping from words to action is genuinely unambiguous — volume,
lock, screenshot, mute, brightness-with-a-number, opening a known app.
Target: a regex match + a direct function call, not a network round trip.

WHY THIS IS SCOPED THE WAY IT IS (read before adding to it):

This is deliberately a SMALL, high-confidence set, not an attempt to
replace the planner. Two rules keep it safe to skip Gemini entirely:

1. Every pattern here maps to exactly ONE possible action with NO
   entity resolution required — no contact names, no fuzzy song titles,
   no "which of these did you mean." If a command needs Gemini's judgment
   to resolve an ambiguity, it doesn't belong in Tier 0, no matter how
   "simple" it feels. "Open camera" is Tier 0 (one exact target). "Play
   Dilbar song" is not (needs search-query construction). "Message Varsha"
   is not (needs contact resolution against a fuzzy name).

2. A miss here is always SAFE, never wrong: if nothing matches,
   `match()` returns None and the caller falls through to the existing
   intent-gate -> planner pipeline exactly as before. This tier can only
   ever make things faster, never change what a command actually does —
   it reuses the exact same `execute_plan()` (reason -> validate ->
   verify) as the planner path, so a "dangerous" action (shutdown,
   restart, delete) still requires confirmation exactly as before. Speed
   changes; safety guarantees do not.

Patterns are built from the SAME sources of truth used elsewhere
(config.settings.WINDOWS_APPS for app names) rather than a second
hardcoded list that could drift out of sync.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from config.settings import WINDOWS_APPS

# Each entry: (compiled regex, tool, action, arg_extractor)
# arg_extractor(match) -> dict of args, or None to reject a "near miss"
# (e.g. brightness with no parseable number) and let it fall through to
# the planner instead of guessing.
_PatternEntry = Tuple[re.Pattern, str, str, Any]

_patterns: Optional[List[_PatternEntry]] = None


def _no_args(_match: "re.Match") -> Dict[str, Any]:
    return {}


def _brightness_args(match: "re.Match") -> Optional[Dict[str, Any]]:
    try:
        level = int(match.group("level"))
    except (TypeError, ValueError):
        return None
    if not (0 <= level <= 100):
        return None
    return {"level": level}


def _open_app_args_factory(app_name: str):
    def _extract(_match: "re.Match") -> Dict[str, Any]:
        return {"app": app_name}
    return _extract


def _open_site_args_factory(site_name: str):
    def _extract(_match: "re.Match") -> Dict[str, Any]:
        return {"site": site_name}
    return _extract


def _build_patterns() -> List[_PatternEntry]:
    patterns: List[_PatternEntry] = [
        # Volume — English + common Hindi/Hinglish phrasing, order-independent
        # would need the fuller synonym-set approach from intent_gate; here
        # we only need the handful of EXACT phrasings common enough to be
        # worth a zero-LLM fast path. Everything else still works fine via
        # the normal planner path — this is a speed bonus, not a rewrite.
        (re.compile(r"^\s*(volume\s+up|awaaz\s+badhao|sound\s+up)\s*[.!]?\s*$", re.I), "volume", "up", _no_args),
        (re.compile(r"^\s*(volume\s+down|awaaz\s+kam\s+karo|sound\s+down)\s*[.!]?\s*$", re.I), "volume", "down", _no_args),
        (re.compile(r"^\s*mute(\s+(it|the\s+volume|karo))?\s*[.!]?\s*$", re.I), "volume", "mute", _no_args),
        (re.compile(r"^\s*unmute(\s+(it|the\s+volume|karo))?\s*[.!]?\s*$", re.I), "volume", "unmute", _no_args),

        # System — lock/screenshot are single-target, no-argument, no
        # ambiguity. Shutdown/restart are included too: they still go
        # through the normal dangerous-action confirmation in
        # execute_plan(), Tier 0 only speeds up GETTING to that
        # confirmation prompt, it doesn't skip it.
        (re.compile(r"^\s*lock(\s+(the\s+)?(laptop|computer|pc|screen))?\s*[.!]?\s*$", re.I), "system", "lock", _no_args),
        (re.compile(r"^\s*(take\s+a\s+)?screenshot\s*[.!]?\s*$", re.I), "screenshot", "default", _no_args),
        (re.compile(r"^\s*shut\s*down(\s+(the\s+)?(laptop|computer|pc))?\s*[.!]?\s*$", re.I), "system", "shutdown", _no_args),
        (re.compile(r"^\s*restart(\s+(the\s+)?(laptop|computer|pc))?\s*[.!]?\s*$", re.I), "system", "restart", _no_args),
        (re.compile(r"^\s*(go\s+to\s+)?sleep\s*[.!]?\s*$", re.I), "system", "sleep", _no_args),

        # Brightness — the ONLY argument here is a plain integer parsed by
        # regex, no fuzzy interpretation, so it's still safe for Tier 0.
        (
            re.compile(r"^\s*(set\s+)?brightness\s+(to\s+)?(?P<level>\d{1,3})\s*%?\s*[.!]?\s*$", re.I),
            "system", "brightness", _brightness_args,
        ),

        # Clipboard
        (re.compile(r"^\s*(read|show)\s+(the\s+)?clipboard\s*[.!]?\s*$", re.I), "clipboard", "read", _no_args),
        (re.compile(r"^\s*clear\s+(the\s+)?clipboard\s*[.!]?\s*$", re.I), "clipboard", "clear", _no_args),

        # WhatsApp Desktop — single-target open, no ambiguity, but it's a
        # standalone tool rather than a config.settings.WINDOWS_APPS entry
        # so it needs its own explicit pattern rather than being picked up
        # by the generic app-opening loop below.
        (re.compile(r"^\s*open\s+(?:the\s+)?whatsapp\s*[.!]?\s*$", re.I), "whatsapp", "open", _no_args),

        # File Explorer — WINDOWS_APPS already maps the bare "explorer",
        # but "file explorer" (the name most people actually say) wasn't
        # matched by that entry's exact-word pattern, so it fell through
        # to the planner for something this unambiguous.
        (
            re.compile(r"^\s*open\s+(?:the\s+)?file\s+explorer\s*[.!]?\s*$", re.I),
            "system", "open_app", _open_app_args_factory("explorer"),
        ),
    ]

    # Open <known app> — built FROM config.settings.WINDOWS_APPS rather
    # than a second hardcoded list, so it can never drift out of sync with
    # what open_app() actually supports.
    for app_key in WINDOWS_APPS:
        escaped = re.escape(app_key)
        pattern = re.compile(rf"^\s*open\s+(?:the\s+)?{escaped}\s*[.!]?\s*$", re.I)
        patterns.append((pattern, "system", "open_app", _open_app_args_factory(app_key)))

    # Open <known website> — same principle, sourced from browser_tool's
    # own _SITES dict rather than a duplicate list here. Single-target,
    # no argument ambiguity (a bare site name, nothing else in the
    # message), so it's genuinely Tier 0 despite touching the browser.
    try:
        from tools.browser_tool import _SITES as _known_sites
    except ImportError:
        _known_sites = {}

    for site_key in _known_sites:
        escaped = re.escape(site_key)
        pattern = re.compile(rf"^\s*open\s+(?:the\s+)?{escaped}\s*[.!]?\s*$", re.I)
        patterns.append((pattern, "browser", "open_site", _open_site_args_factory(site_key)))

    return patterns


def _get_patterns() -> List[_PatternEntry]:
    global _patterns
    if _patterns is None:
        _patterns = _build_patterns()
    return _patterns


def refresh_patterns() -> None:
    """Call if WINDOWS_APPS or the pattern set changes at runtime (normally
    unnecessary — built once from static config at first use)."""
    global _patterns
    _patterns = None


def match(message: str) -> Optional[Dict[str, Any]]:
    """Return a ready-to-execute plan step ({"tool", "args"}) if `message`
    unambiguously matches a Tier 0 pattern, else None. None means: fall
    through to the normal intent-gate -> planner pipeline, exactly as if
    this module didn't exist — this function can only ever short-circuit
    to a FASTER path, never to a different outcome than the planner would
    have reached for these same unambiguous phrasings."""
    text = (message or "").strip()
    if not text:
        return None

    for pattern, tool, action_name, arg_extractor in _get_patterns():
        m = pattern.match(text)
        if not m:
            continue
        extracted = arg_extractor(m)
        if extracted is None:
            continue  # near-miss (e.g. unparseable number) — let planner handle it
        return {"tool": tool, "args": {"action": action_name, **extracted}}

    return None