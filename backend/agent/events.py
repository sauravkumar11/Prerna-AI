"""
Events
======
The generic event model + initial event type catalogue for Prerna Core
v1.2's Event Bus.

Per the v1.2 scope: these event types are DEFINED here so future modules
have a shared vocabulary to publish/subscribe against, but nothing in the
existing codebase is required to use them yet. This file has zero
dependencies on planner/executor/memory/voice/browser internals — it can
be imported anywhere without risk of circular imports or coupling.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class EventType(str, Enum):
    """Initial event catalogue (v1.2 scope). Values are plain strings
    (this is a str Enum) so publish()/subscribe() can be called with
    either `EventType.USER_COMMAND` or the bare string `"user_command"` —
    useful for a future module that doesn't want an import dependency on
    this file, without losing type-checking for the ones that do."""

    USER_COMMAND = "user_command"
    PLAN_CREATED = "plan_created"
    TOOL_EXECUTED = "tool_executed"
    TOOL_FAILED = "tool_failed"
    TASK_COMPLETED = "task_completed"
    VOICE_STARTED = "voice_started"
    VOICE_STOPPED = "voice_stopped"
    BROWSER_OPENED = "browser_opened"
    MEMORY_UPDATED = "memory_updated"
    NOTIFICATION_ARRIVED = "notification_arrived"
    APPLICATION_FOCUSED = "application_focused"


def _current_trace_id_or_none() -> Optional[str]:
    """Reuses the existing request-tracing system (utils/trace.py) from
    v1.1.1 rather than inventing a second correlation-id mechanism. Import
    is deferred (not at module load) so this module never fails to import
    even if utils.trace ever changes shape — events should be able to
    exist independently of the tracing subsystem."""
    try:
        from utils.trace import current_trace_id
        trace_id = current_trace_id()
        return None if trace_id == "-" else trace_id
    except Exception:
        return None


@dataclass
class Event:
    """Generic event envelope. Every field except `event_type` has a
    sensible default, so callers can do `Event(EventType.USER_COMMAND,
    payload={...})` without filling in boilerplate every time.

    Fields:
        event_type: which kind of event this is (EventType or a bare str
            for forward-compatibility with types not yet added here).
        payload: the actual event data — shape is intentionally
            unconstrained (Any), since different event types carry
            different data and this module shouldn't need to know about
            every consumer's expectations.
        event_id: unique id for this specific event instance.
        timestamp: unix time the event was created.
        source: which module/component published this (e.g. "planner",
            "voice"). Free-form string, not enforced against a fixed list.
        metadata: free-form extra context (severity, tags, whatever a
            future publisher wants) without needing to extend this class.
        trace_id: the current request's trace ID if one is active (see
            utils/trace.py) — lets you correlate an event back to the
            specific /chat request that caused it, in logs.
    """

    event_type: "EventType | str"
    payload: Any = None
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
    source: str = ""
    metadata: dict = field(default_factory=dict)
    trace_id: Optional[str] = field(default_factory=_current_trace_id_or_none)

    def __post_init__(self) -> None:
        # Normalize to the plain string value so subscribers comparing
        # against EventType.X or the bare string both work identically —
        # `EventType.USER_COMMAND == "user_command"` is True (str Enum),
        # but storing the raw value avoids any confusion in logs/dict keys.
        if isinstance(self.event_type, EventType):
            self.event_type = self.event_type.value