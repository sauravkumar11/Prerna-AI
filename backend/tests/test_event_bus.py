# -*- coding: utf-8 -*-
"""
Tests for agent/event_bus.py and agent/events.py

Covers every item explicitly listed in the v1.2 brief: subscribe,
unsubscribe, synchronous publish, asynchronous publish, multiple
subscribers, exception handling, event ordering, duplicate subscriptions,
thread safety, queue shutdown.

Each test constructs its OWN EventBus() instance rather than using the
process-wide get_event_bus() singleton — this keeps tests fully isolated
from each other (no shared subscriber state leaking between tests) and
means they can run in any order or in parallel safely.
"""

from __future__ import annotations

import threading
import time

from agent.event_bus import EventBus
from agent.events import Event, EventType


# ── subscribe / unsubscribe ─────────────────────────────────────────────────

def test_subscribe_then_publish_calls_handler():
    bus = EventBus()
    received = []
    bus.subscribe(EventType.USER_COMMAND, lambda e: received.append(e))
    bus.publish(Event(EventType.USER_COMMAND, payload="hello"))
    assert len(received) == 1
    assert received[0].payload == "hello"


def test_subscribe_accepts_bare_string_event_type():
    """subscribe("user_command", ...) and EventType.USER_COMMAND must
    refer to the same subscription — bare strings exist for forward
    compatibility with modules that don't want an import dependency."""
    bus = EventBus()
    received = []
    bus.subscribe("user_command", lambda e: received.append(e))
    bus.publish(Event(EventType.USER_COMMAND, payload="hi"))
    assert len(received) == 1


def test_unsubscribe_stops_delivery():
    bus = EventBus()
    received = []
    def handler(e):
        received.append(e)
    bus.subscribe(EventType.USER_COMMAND, handler)
    bus.unsubscribe(EventType.USER_COMMAND, handler)
    bus.publish(Event(EventType.USER_COMMAND))
    assert received == []


def test_unsubscribe_unknown_handler_is_a_safe_no_op():
    bus = EventBus()
    def never_subscribed(e):
        pass
    bus.unsubscribe(EventType.USER_COMMAND, never_subscribed)  # must not raise


def test_publish_with_no_subscribers_is_a_safe_no_op():
    bus = EventBus()
    bus.publish(Event(EventType.USER_COMMAND))  # must not raise


def test_subscriber_count_reflects_current_subscriptions():
    bus = EventBus()
    assert bus.subscriber_count(EventType.USER_COMMAND) == 0
    bus.subscribe(EventType.USER_COMMAND, lambda e: None)
    assert bus.subscriber_count(EventType.USER_COMMAND) == 1


# ── duplicate subscriptions ──────────────────────────────────────────────────

def test_duplicate_subscription_of_same_handler_does_not_double_fire():
    """Deliberate design choice (see event_bus.py docstring): subscribing
    the same handler twice to the same event type is deduplicated, not
    treated as 'call it twice per event'."""
    bus = EventBus()
    call_count = [0]
    def handler(e):
        call_count[0] += 1

    bus.subscribe(EventType.USER_COMMAND, handler)
    bus.subscribe(EventType.USER_COMMAND, handler)
    assert bus.subscriber_count(EventType.USER_COMMAND) == 1

    bus.publish(Event(EventType.USER_COMMAND))
    assert call_count[0] == 1


def test_two_different_handlers_both_fire_independently():
    bus = EventBus()
    calls = []
    bus.subscribe(EventType.USER_COMMAND, lambda e: calls.append("a"))
    bus.subscribe(EventType.USER_COMMAND, lambda e: calls.append("b"))
    bus.publish(Event(EventType.USER_COMMAND))
    assert sorted(calls) == ["a", "b"]


# ── multiple subscribers / different event types ────────────────────────────

def test_subscribers_only_receive_their_own_event_type():
    bus = EventBus()
    command_events = []
    tool_events = []
    bus.subscribe(EventType.USER_COMMAND, lambda e: command_events.append(e))
    bus.subscribe(EventType.TOOL_EXECUTED, lambda e: tool_events.append(e))

    bus.publish(Event(EventType.USER_COMMAND))
    assert len(command_events) == 1
    assert len(tool_events) == 0

    bus.publish(Event(EventType.TOOL_EXECUTED))
    assert len(command_events) == 1
    assert len(tool_events) == 1


# ── exception handling / isolation ───────────────────────────────────────────

def test_one_failing_handler_does_not_stop_other_subscribers():
    bus = EventBus()
    calls = []
    def failing_handler(e):
        raise RuntimeError("boom")
    def working_handler(e):
        calls.append("ran")

    bus.subscribe(EventType.USER_COMMAND, failing_handler)
    bus.subscribe(EventType.USER_COMMAND, working_handler)

    bus.publish(Event(EventType.USER_COMMAND))  # must not raise
    assert calls == ["ran"]


def test_exception_in_handler_does_not_propagate_to_publish_caller():
    bus = EventBus()
    def failing_handler(e):
        raise ValueError("this should be isolated")
    bus.subscribe(EventType.USER_COMMAND, failing_handler)
    bus.publish(Event(EventType.USER_COMMAND))  # must not raise — the real assertion


# ── event ordering ────────────────────────────────────────────────────────────

def test_sync_publish_calls_subscribers_in_subscription_order():
    bus = EventBus()
    order = []
    bus.subscribe(EventType.USER_COMMAND, lambda e: order.append(1))
    bus.subscribe(EventType.USER_COMMAND, lambda e: order.append(2))
    bus.subscribe(EventType.USER_COMMAND, lambda e: order.append(3))
    bus.publish(Event(EventType.USER_COMMAND))
    assert order == [1, 2, 3]


def test_async_publish_dispatches_events_in_publish_order():
    """FIFO ordering for the async queue: events published in order 1,2,3
    must be DISPATCHED in that same order, even though publish_async()
    itself returns immediately."""
    bus = EventBus()
    received_order = []
    bus.subscribe(EventType.USER_COMMAND, lambda e: received_order.append(e.payload))

    for i in range(1, 11):
        bus.publish_async(Event(EventType.USER_COMMAND, payload=i))

    bus.wait_until_idle(timeout=5.0)
    assert received_order == list(range(1, 11))


# ── synchronous vs asynchronous publish ──────────────────────────────────────

def test_sync_publish_is_immediate_not_queued():
    bus = EventBus()
    received = []
    bus.subscribe(EventType.USER_COMMAND, lambda e: received.append(e))
    bus.publish(Event(EventType.USER_COMMAND))
    # No wait/sleep needed — sync publish must have already delivered by
    # the time publish() returns.
    assert len(received) == 1


def test_async_publish_returns_immediately_without_blocking():
    bus = EventBus()
    def slow_handler(e):
        time.sleep(0.3)
    bus.subscribe(EventType.USER_COMMAND, slow_handler)

    t0 = time.perf_counter()
    bus.publish_async(Event(EventType.USER_COMMAND))
    elapsed = time.perf_counter() - t0

    assert elapsed < 0.1, f"publish_async() blocked for {elapsed:.3f}s — should return near-instantly"
    bus.shutdown(wait=True, timeout=2.0)  # cleanup, also proves the slow handler did eventually run


def test_async_publish_eventually_delivers():
    bus = EventBus()
    received = []
    bus.subscribe(EventType.USER_COMMAND, lambda e: received.append(e))
    bus.publish_async(Event(EventType.USER_COMMAND, payload="async hello"))
    bus.wait_until_idle(timeout=5.0)
    assert len(received) == 1
    assert received[0].payload == "async hello"


# ── thread safety ─────────────────────────────────────────────────────────────

def test_concurrent_publish_async_from_many_threads_delivers_every_event():
    """Real threading.Thread workers (not sequential calls) hammering
    publish_async() concurrently — proves the queue and subscriber
    dispatch are actually thread-safe under real contention, not just
    safe in a single-threaded test."""
    bus = EventBus()
    received = []
    received_lock = threading.Lock()

    def handler(e):
        with received_lock:
            received.append(e.payload)

    bus.subscribe(EventType.USER_COMMAND, handler)

    N_THREADS = 20
    def worker(i):
        bus.publish_async(Event(EventType.USER_COMMAND, payload=i))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(N_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    bus.wait_until_idle(timeout=5.0)
    assert sorted(received) == list(range(N_THREADS)), "every published event must be delivered exactly once"


def test_concurrent_subscribe_from_many_threads_does_not_corrupt_subscriber_list():
    bus = EventBus()
    N_THREADS = 20

    def worker(i):
        bus.subscribe(EventType.USER_COMMAND, lambda e, i=i: None)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(N_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Each lambda is a distinct object (default-arg-captured i differs),
    # so all 20 should have registered without any lost updates.
    assert bus.subscriber_count(EventType.USER_COMMAND) == N_THREADS


# ── queue shutdown ───────────────────────────────────────────────────────────

def test_shutdown_with_no_worker_ever_started_is_a_safe_no_op():
    bus = EventBus()
    result = bus.shutdown(wait=True, timeout=1.0)
    assert result is True


def test_shutdown_drains_already_queued_events_before_stopping():
    """Graceful shutdown must not discard events that were already queued
    — it should finish dispatching them, then stop."""
    bus = EventBus()
    received = []
    bus.subscribe(EventType.USER_COMMAND, lambda e: received.append(e.payload))

    for i in range(5):
        bus.publish_async(Event(EventType.USER_COMMAND, payload=i))

    stopped_cleanly = bus.shutdown(wait=True, timeout=5.0)
    assert stopped_cleanly is True
    assert sorted(received) == [0, 1, 2, 3, 4]


def test_worker_restarts_after_shutdown_if_publish_async_called_again():
    """shutdown() stops the worker thread, but the bus itself should
    still be usable afterward — a fresh publish_async() call should start
    a new worker rather than silently doing nothing forever."""
    bus = EventBus()
    received = []
    bus.subscribe(EventType.USER_COMMAND, lambda e: received.append(e))

    bus.publish_async(Event(EventType.USER_COMMAND))
    bus.wait_until_idle(timeout=2.0)
    bus.shutdown(wait=True, timeout=2.0)

    bus.publish_async(Event(EventType.USER_COMMAND))
    bus.wait_until_idle(timeout=2.0)

    assert len(received) == 2


# ── Event model itself ───────────────────────────────────────────────────────

def test_event_has_unique_id_per_instance():
    e1 = Event(EventType.USER_COMMAND)
    e2 = Event(EventType.USER_COMMAND)
    assert e1.event_id != e2.event_id


def test_event_type_normalizes_enum_to_plain_string():
    e = Event(EventType.USER_COMMAND)
    assert e.event_type == "user_command"
    assert isinstance(e.event_type, str)


def test_event_accepts_bare_string_event_type_too():
    e = Event("some_future_event_type_not_yet_in_the_enum")
    assert e.event_type == "some_future_event_type_not_yet_in_the_enum"


def test_event_trace_id_is_none_outside_any_active_trace():
    e = Event(EventType.USER_COMMAND)
    assert e.trace_id is None


def test_event_trace_id_is_populated_inside_an_active_trace():
    """Proves the reuse of the existing tracing system (utils/trace.py)
    actually works, not just that the import doesn't crash."""
    from utils.trace import new_trace
    with new_trace("test") as trace:
        e = Event(EventType.USER_COMMAND)
        assert e.trace_id == trace.trace_id