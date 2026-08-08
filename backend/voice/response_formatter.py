"""
Response Formatter
===================
Strips implementation-detail noise (raw YouTube titles, Windows file
paths, URLs, window-title strings) out of whatever text is about to be
spoken, WITHOUT touching a single tool file.

Why this doesn't require editing 20 tools: `ToolResult` already has a
`speech` field separate from `message` for exactly this purpose (see its
docstring — "Playing Dilbar." instead of a full YouTube title is the
example already written there). The gap isn't the mechanism, it's that
most tools never set `speech=`, so `chat.py`'s `speech = tool_result.speech
or tool_result.message` falls through to the raw message. Rather than
touching every tool that has this gap (real risk of regressions across
20 files for a "don't change tool functionality" requirement), this
module is a single new layer, applied at the exact same choke point
voice.naturalizer already uses (tts.py's generate_audio) — so every
tool's spoken output gets cleaned up automatically, tools that already
set a good `speech=` are left alone (their text won't match any of these
"raw junk" patterns, so every rule here is a safe no-op on it), and no
other file needs to change.

Ordering: this runs BEFORE naturalize_for_speech — semantic cleanup
first (what should be said), phrasing polish second (how it should
sound). Each rule below is conservative on purpose: it only fires on a
recognizable "raw junk" shape (a Windows path, an http(s) URL, a
Playing-prefixed quoted title, a Window-title-prefixed string) and
returns the ORIGINAL text unchanged if nothing matches — this is a
targeted cleanup pass, not a general summarizer, and guessing wrong on
text that isn't actually junk would be worse than leaving it alone.
"""

from __future__ import annotations

import re
from pathlib import PureWindowsPath
from typing import Optional
from urllib.parse import urlparse

# ── YouTube / media titles ──────────────────────────────────────────────

_YOUTUBE_JUNK_WORDS = {
    "official", "video", "audio", "lyrical", "lyrics", "full", "song",
    "hd", "4k", "music", "mv", "movie", "trailer", "new", "latest",
    "original", "remix", "cover", "live", "version",
}

_PLAYING_RE = re.compile(r'^(playing)\s+"?(.+?)"?[.!]?\s*$', re.IGNORECASE)


def _clean_media_title(text: str) -> Optional[str]:
    match = _PLAYING_RE.match(text.strip())
    if not match:
        return None
    verb, raw_title = match.groups()

    if "http" in raw_title.lower() or "www." in raw_title.lower():
        return None  # a URL got passed as if it were a title — let _clean_url handle it instead

    # Take the first chunk before a common delimiter — YouTube titles pile
    # everything (artist, movie, descriptor tags) after a |, -, (, or [.
    first_chunk = re.split(r"\s*[\|\u2013\u2014\-]\s*|\s*[\(\[]", raw_title)[0].strip()
    words = first_chunk.split()

    while words and re.sub(r"[.,!]+$", "", words[-1]).lower() in _YOUTUBE_JUNK_WORDS:
        words.pop()

    if not words:
        words = raw_title.split()[:3]  # everything got stripped as junk — fall back to a short prefix

    title = " ".join(words).strip()
    if title.isupper() or title.islower():
        title = title.title()  # "DILBAR" / "dilbar" -> "Dilbar"; leave already-mixed-case titles alone

    return f"{verb.capitalize()} {title}." if title else None


# ── Windows file paths ───────────────────────────────────────────────────

_WIN_PATH_RE = re.compile(
    r'((?:[A-Za-z]:|\\\\[^\\/:*?"<>|\r\n]+)\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]+)'
)

_FILENAME_NOISE_RE = re.compile(
    r"\b(v\d+|final|latest|copy|new|old|draft|version|updated|\d{4,})\b", re.IGNORECASE
)


def _clean_file_path(text: str) -> Optional[str]:
    match = _WIN_PATH_RE.search(text)
    if not match:
        return None

    filename = PureWindowsPath(match.group(1)).stem
    friendly = re.sub(r"[_\-]+", " ", filename)
    friendly = _FILENAME_NOISE_RE.sub("", friendly)
    friendly = re.sub(r"\s+", " ", friendly).strip().lower()

    verb = "opened" if re.search(r"\bopen(ed|ing)?\b", text, re.IGNORECASE) else "done with"

    if not friendly:
        return f"I have {verb} that file."
    # Short, humanized filename ("resume", "quarterly report") reads
    # naturally as "your X"; anything longer just gets called "the file"
    # rather than reading a whole cleaned-up phrase as if it were a name.
    if len(friendly.split()) <= 3:
        return f"I have {verb} your {friendly}."
    return f"I have {verb} the file."


# ── URLs ──────────────────────────────────────────────────────────────────

_URL_RE = re.compile(r'https?://[^\s"\')\]]+')

_FRIENDLY_SITES = {
    "youtube.com": "YouTube", "youtu.be": "YouTube",
    "mail.google.com": "Gmail", "gmail.com": "Gmail",
    "chatgpt.com": "ChatGPT", "claude.ai": "Claude",
    "gemini.google.com": "Gemini", "github.com": "GitHub",
    "google.com": "Google", "maps.google.com": "Maps",
    "calendar.google.com": "Calendar", "teams.microsoft.com": "Teams",
    "outlook.com": "Outlook", "linkedin.com": "LinkedIn",
    "instagram.com": "Instagram", "facebook.com": "Facebook",
    "spotify.com": "Spotify", "open.spotify.com": "Spotify",
    "netflix.com": "Netflix", "stackoverflow.com": "Stack Overflow",
    "duckduckgo.com": "DuckDuckGo",
}


def _clean_url(text: str) -> Optional[str]:
    match = _URL_RE.search(text)
    if not match:
        return None

    domain = urlparse(match.group(0)).netloc.lower()
    domain = re.sub(r"^www\.", "", domain)
    friendly = _FRIENDLY_SITES.get(domain)
    if not friendly:
        main_label = domain.split(".")[0]
        friendly = main_label.capitalize() if main_label else "that site"

    verb = "Opening" if re.search(r"\bopen(ing)?\b", text, re.IGNORECASE) else "Going to"
    return f"{verb} {friendly}."


# ── Window titles ─────────────────────────────────────────────────────────

_WINDOW_TITLE_RE = re.compile(
    r'^(?:window title:\s*|successfully switched to\s*)(.+)$', re.IGNORECASE
)


def _clean_window_title(text: str) -> Optional[str]:
    match = _WINDOW_TITLE_RE.match(text.strip())
    if not match:
        return None
    title = match.group(1)
    # Strip trailing " - project name" / " — process.exe" style suffixes
    # window managers commonly append after the actual app name.
    title = re.split(r"\s+[\-\u2013\u2014]\s+", title)[0].strip().rstrip(".")
    return f"Opening {title}." if title else None


# ── Generic fallback for long technical strings nothing else caught ──────

_FALLBACK_WORD_LIMIT = 10


def _fallback_shorten(text: str) -> str:
    words = text.split()
    if len(words) <= _FALLBACK_WORD_LIMIT:
        return text  # short enough already — not everything needs a rule to match
    return " ".join(words[:_FALLBACK_WORD_LIMIT]).rstrip(".,;:") + "."


# ── Entry point ───────────────────────────────────────────────────────────

_CLEANERS = (_clean_media_title, _clean_window_title, _clean_url, _clean_file_path)


def format_for_speech(text: str) -> str:
    """The only function callers need. Tries each targeted cleaner in
    order; the first one whose pattern actually matches wins. Falls back
    to a soft length cap only if nothing recognizable matched at all —
    never guesses at restructuring text that isn't clearly one of the
    known raw-junk shapes."""
    if not text or not text.strip():
        return text

    for cleaner in _CLEANERS:
        cleaned = cleaner(text)
        if cleaned:
            return cleaned

    return _fallback_shorten(text)