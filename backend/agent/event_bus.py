"""
Event Bus
=========
Publish/subscribe infrastructure for Prerna Core v1.2.

DESIGN DECISION (stated explicitly per the v1.2 brief's own instruction to
explain assumptions before implementing rather than making breaking
changes): the async queue is built on `queue.Queue` + a background
`threading.Thread`, NOT `asyncio`. Most of this codebase is fundamentally
synchronous (e.g. /chat is a sync FastAPI route run in Starlette's thread
pool) — an asyncio-based queue would only work correctly when called from
inside a running event loop, which is awkward and easy to misuse from sync
code. `queue.Queue` is thread-safe by construction and callable identically
from sync or async contexts with no event-loop dependency. This trades
"modern asyncio" for "actually fits the codebase as it exists today."

BACKWARD COMPATIBILITY: this module has zero side effects on import beyond
creating one background thread (started lazily, on first use — not at
import time). Nothing in the existing planner/executor/memory/voice/
browser modules is required to change. See docs/ARCHITECTURE.md for the
one deliberate, minimal integration point (Planner -> publish(UserCommand)
-> Executor subscribes) added in this version.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Callable, Dict, List, Optional

from agent.events import Event
from utils.logger import get_logger

logger = get_logger(__name__)

Handler = Callable[[Event], None]

# Sentinel placed on the queue to signal the worker thread to stop —
# distinct from any real Event, and never delivered to a subscriber.
_SHUTDOWN_SENTINEL = object()


class EventBus:
    """One process-wide event bus. Use `get_event_bus()` to get the
    shared singleton rather than instantiating this directly — tests can
    still construct their own instance for isolation (see
    tests/test_event_bus.py)."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Handler]] = {}
        self._lock = threading.Lock()

        self._queue: "queue.Queue" = queue.Queue()
        self._worker_thread: Optional[threading.Thread] = None
        self._worker_lock = threading.Lock()
        self._shutting_down = False

    # ── Subscription management ─────────────────────────────────────────

    def subscribe(self, event_type: "str | object", handler: Handler) -> None:
        """Register `handler` to be called for every event of
        `event_type`. Subscribing the SAME handler to the SAME event type
        more than once is a no-op (deduplicated) — this is a deliberate
        choice to prevent a handler accidentally firing twice from a
        double-registration bug, which is a much easier mistake to make
        than genuinely wanting one handler called twice per event."""
        key = _event_type_key(event_type)
        with self._lock:
            bucket = self._subscribers.setdefault(key, [])
            if handler not in bucket:
                bucket.append(handler)
                logger.debug("Subscribed %r to event type %r", getattr(handler, "__name__", handler), key)

    def unsubscribe(self, event_type: "str | object", handler: Handler) -> None:
        """Remove `handler` from `event_type`'s subscriber list. Safe to
        call even if the handler was never subscribed (no-op, not an
        error) — callers shouldn't need to track subscription state just
        to clean up safely."""
        key = _event_type_key(event_type)
        with self._lock:
            bucket = self._subscribers.get(key)
            if bucket and handler in bucket:
                bucket.remove(handler)
                logger.debug("Unsubscribed %r from event type %r", getattr(handler, "__name__", handler), key)

    def subscriber_count(self, event_type: "str | object") -> int:
        """Mainly for tests/observability — how many handlers are
        currently registered for a given event type."""
        key = _event_type_key(event_type)
        with self._lock:
            return len(self._subscribers.get(key, []))

    # ── Publishing ───────────────────────────────────────────────────────

    def publish(self, event: Event) -> None:
        """Synchronous, immediate dispatch — every subscriber for
        event.event_type is called right now, in this thread, in
        subscription order. Each subscriber is isolated: an exception in
        one handler is logged and does NOT stop the remaining subscribers
        from running, and does NOT propagate to the caller of publish()."""
        key = _event_type_key(event.event_type)
        with self._lock:
            handlers = list(self._subscribers.get(key, []))  # snapshot — see note below

        for handler in handlers:
            self._dispatch_one(handler, event)

    def publish_async(self, event: Event) -> None:
        """Non-blocking: puts the event on the internal queue and returns
        immediately. A background worker thread (started lazily on first
        use) dispatches it in the order it was enqueued, same per-handler
        exception isolation as publish(). Safe to call from any thread."""
        self._ensure_worker_running()
        self._queue.put(event)

    def _dispatch_one(self, handler: Handler, event: Event) -> None:
        try:
            handler(event)
        except Exception:
            logger.exception(
                "Event handler %r raised while handling event_type=%r (event_id=%s) — "
                "isolated, other subscribers still ran normally.",
                getattr(handler, "__name__", handler), event.event_type, event.event_id,
            )

    # ── Async worker lifecycle ───────────────────────────────────────────

    def _ensure_worker_running(self) -> None:
        # Double-checked locking: cheap fast path (no lock) for the common
        # case where the worker's already running, lock only needed once
        # at first-ever publish_async() call.
        if self._worker_thread is not None and self._worker_thread.is_alive():
            return
        with self._worker_lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return
            self._shutting_down = False
            self._worker_thread = threading.Thread(
                target=self._worker_loop, name="EventBus-worker", daemon=True,
            )
            self._worker_thread.start()
            logger.debug("EventBus async worker thread started.")

    def _worker_loop(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is _SHUTDOWN_SENTINEL:
                    return
                event = item
                key = _event_type_key(event.event_type)
                with self._lock:
                    handlers = list(self._subscribers.get(key, []))
                for handler in handlers:
                    self._dispatch_one(handler, event)
            finally:
                self._queue.task_done()

    def shutdown(self, wait: bool = True, timeout: Optional[float] = 5.0) -> bool:
        """Gracefully stop the async worker: no new events are dispatched
        after this returns (if wait=True), but this does NOT discard
        events already queued — the worker drains them first, then stops.
        Safe to call even if publish_async() was never used (no-op).
        Returns True if the worker stopped cleanly within `timeout`,
        False if it's still running when this returns (caller can decide
        whether that's acceptable)."""
        with self._worker_lock:
            if self._worker_thread is None or not self._worker_thread.is_alive():
                return True
            self._shutting_down = True
            self._queue.put(_SHUTDOWN_SENTINEL)
            thread = self._worker_thread

        if wait:
            thread.join(timeout=timeout)
            stopped = not thread.is_alive()
            if stopped:
                logger.debug("EventBus async worker thread stopped cleanly.")
            else:
                logger.warning("EventBus async worker did not stop within %.1fs.", timeout or 0.0)
            return stopped
        return True

    def wait_until_idle(self, timeout: Optional[float] = None) -> bool:
        """Block until every currently-queued async event has been
        dispatched (queue.Queue.join() semantics). Mainly useful for
        tests that need a deterministic point to assert on results from
        publish_async() without sleeping/polling."""
        if timeout is None:
            self._queue.join()
            return True
        deadline = time.time() + timeout
        while not self._queue.unfinished_tasks == 0:
            if time.time() >= deadline:
                return False
            time.sleep(0.01)
        return True


def _event_type_key(event_type: "str | object") -> str:
    """Normalizes EventType members and bare strings to the same dict key
    so `subscribe(EventType.USER_COMMAND, ...)` and
    `subscribe("user_command", ...)` refer to the same subscription."""
    value = getattr(event_type, "value", event_type)
    return str(value)


_bus: Optional[EventBus] = None
_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """Process-wide singleton — this is what every module should use
    unless it specifically needs an isolated instance (tests)."""
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = EventBus()
    return _bus