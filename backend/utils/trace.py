"""
Trace
=====
Per-request Trace ID + stage timing, propagated automatically through
EVERY existing logger.info()/warning()/etc. call anywhere in the codebase
via contextvars — no function signatures change, no call sites need a
trace_id parameter threaded through them. This is what makes it possible
to satisfy "every log should include the Trace ID" without touching
public APIs or unrelated code: attach a logging.Filter (see
utils/logger.py) that reads the current trace ID from the contextvar, and
every module's existing `logger = get_logger(__name__)` calls just start
including it for free.

Also serves as the "Performance Monitor" from the v1.1 brief: each named
stage is timed, and — the concrete, testable version of "detect duplicate
Gemini calls / repeated browser creation" — a WARNING is logged if the
same stage name is entered more than once within a single request trace.
A well-behaved request shouldn't call Gemini or launch a browser twice;
if it does, that's exactly the kind of accidental duplicate work this is
meant to surface.

Usage:
    trace = new_trace("chat: play dilbar song")
    with trace.stage("context_load"):
        ...
    with trace.stage("gemini_chat_call"):
        ...
    logger.info(trace.summary())
    # -> [a1b2c3d4] chat: play dilbar song | total=1842ms | context_load=12ms, gemini_chat_call=1798ms
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Dict, List, Optional, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)

_current_trace_id: ContextVar[Optional[str]] = ContextVar("current_trace_id", default=None)


def current_trace_id() -> str:
    """Read by the logging filter — '-' when no trace is active (e.g. a
    log line during startup, before any request has come in)."""
    return _current_trace_id.get() or "-"


class Trace:
    def __init__(self, trace_id: str, label: str) -> None:
        self.trace_id = trace_id
        self.label = label
        self.stages: List[Tuple[str, float]] = []
        self._stage_counts: Dict[str, int] = {}
        self._t0 = time.perf_counter()

    @contextmanager
    def stage(self, name: str):
        """Time a named block. If this stage name has already been
        entered once in this same trace, logs a WARNING immediately —
        that's the duplicate-work signal (e.g. Gemini called twice for
        one user message, or a browser session launched twice)."""
        self._stage_counts[name] = self._stage_counts.get(name, 0) + 1
        if self._stage_counts[name] > 1:
            logger.warning(
                "Duplicate work detected: stage '%s' entered %dx in one request (trace=%s)",
                name, self._stage_counts[name], self.trace_id,
            )

        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.stages.append((name, (time.perf_counter() - t0) * 1000))

    def total_ms(self) -> float:
        return (time.perf_counter() - self._t0) * 1000

    def summary(self) -> str:
        total = self.total_ms()
        if not self.stages:
            return f"[{self.trace_id}] {self.label} | total={total:.0f}ms | (no stages recorded — early-return fast path)"
        parts = ", ".join(f"{name}={dur:.0f}ms" for name, dur in self.stages)
        return f"[{self.trace_id}] {self.label} | total={total:.0f}ms | {parts}"


@contextmanager
def new_trace(label: str):
    """Start a new trace for one request: generates a short unique trace
    ID, makes it available to every log line in this request (and
    anything it calls, anywhere in the codebase) via the contextvar, and
    resets the contextvar back to its previous value on exit so traces
    from concurrent/nested requests never bleed into each other.

    Usage as a context manager (recommended — guarantees cleanup):
        with new_trace("chat: hello") as trace:
            with trace.stage("..."):
                ...
            logger.info(trace.summary())
    """
    trace_id = uuid.uuid4().hex[:8]
    token = _current_trace_id.set(trace_id)
    trace = Trace(trace_id, label)
    try:
        yield trace
    finally:
        _current_trace_id.reset(token)