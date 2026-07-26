"""
Intent Gate
===========
For a plain conversational message ("I'm tired today", "dekha wo thoda
dekha wo"), the old flow made TWO Gemini calls: one to plan() (which just
concludes "no tool, this is chat") and a second to generate the actual
reply. Under quota pressure that's twice the cost and twice the chance of
hitting a 429 for something that never needed the planner at all.

`looks_like_tool_request()` is a cheap, local, no-LLM pre-check: does this
message contain ANY vocabulary that plausibly maps to a real tool action?
If not, chat.py skips straight to the conversational reply and never calls
plan() in the first place.

Vocabulary is NOT a hardcoded fixed list living in this file — it's derived
from the tool registry itself (tool names + action names + words pulled out
of each action's own description), so it automatically stays in sync as
tools are added/removed/renamed. A small supplementary set of bilingual
command verbs is layered on top, since the registry's descriptions are
English-only but Saurav mixes Hindi/English — that's language coverage,
not per-assistant hardcoding.

This is intentionally conservative: a false NEGATIVE just means an
ordinary tool command takes the normal (planner) path, same as before —
no behavior change, no risk. A false POSITIVE just means an ordinary chat
message makes one wasted planner call that concludes "chat" — also the
existing behavior today. The gate can only ever save calls, never break one.
"""

from __future__ import annotations

import re
from typing import Set

from agent.registry import get_registry

# Common English stopwords that would otherwise pollute the vocabulary
# pulled from action descriptions (e.g. "a", "the", "with", "to").
_STOPWORDS = {
    "a", "an", "the", "to", "of", "in", "on", "for", "with", "and", "or",
    "is", "it", "this", "that", "your", "you", "at", "by", "as", "be",
    "do", "does", "if", "so", "not", "will", "can", "start", "specific",
    "without", "instead", "using",
}

# Bilingual command verbs/particles — these signal "this is an instruction
# to DO something", regardless of which specific tool. Not tied to any
# specific assistant name or persona; purely functional Hindi/English verb
# coverage so the gate doesn't only work for English phrasing.
_COMMAND_SIGNAL_WORDS = {
    "open", "close", "start", "stop", "kholo", "khol", "band", "karo",
    "kar do", "karde", "bhejo", "bhej do", "send", "call", "message",
    "msg", "play", "pause", "lock", "unlock", "shutdown", "restart",
    "volume", "awaaz", "awaz", "sound", "brightness", "screenshot",
    "mute", "unmute", "block", "unblock", "archive", "pin", "unpin",
    "delete", "mita do", "search", "dhundo", "khoj", "set", "lagao",
    "alarm", "reminder", "note", "likho", "capture", "photo", "video",
    "call karo",
}

_WORD_RE = re.compile(r"[a-zA-Z]{3,}")

_vocab_cache: Set[str] | None = None


def _build_vocab() -> Set[str]:
    vocab: Set[str] = set(_COMMAND_SIGNAL_WORDS)

    for tool in get_registry().values():
        vocab.add(tool.name.lower())
        for act in tool.actions.values():
            vocab.add(act.name.lower().replace("_", " "))
            for word in _WORD_RE.findall(act.name.lower()):
                if word not in _STOPWORDS:
                    vocab.add(word)
            for word in _WORD_RE.findall(act.description.lower()):
                if word not in _STOPWORDS and len(word) >= 4:
                    vocab.add(word)

    return vocab


def _get_vocab() -> Set[str]:
    global _vocab_cache
    if _vocab_cache is None:
        _vocab_cache = _build_vocab()
    return _vocab_cache


def refresh_vocab() -> None:
    """Call if tools are registered dynamically after startup (normally
    unnecessary — tools/__init__.py registers everything at import time)."""
    global _vocab_cache
    _vocab_cache = None


def looks_like_tool_request(message: str) -> bool:
    """True if the message plausibly needs a tool and should go through
    plan(). False means: skip the planner call entirely, treat as chat."""
    text = (message or "").lower()
    if not text.strip():
        return False

    vocab = _get_vocab()

    # Multi-word phrases (e.g. "kar do") first, since a token split would miss them.
    for phrase in vocab:
        if " " in phrase and phrase in text:
            return True

    tokens = set(_WORD_RE.findall(text)) | set(text.split())
    return bool(tokens & vocab)