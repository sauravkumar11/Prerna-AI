# Prerna Architecture

Current Version

Prerna Core v1.2

## Philosophy

Incremental evolution.

Every architectural improvement should preserve existing functionality.

Never perform massive rewrites.

---

## Current Architecture

Frontend

↓

API

↓

Conversation

↓

Planner

↓

Executor

↓

Tools

↓

Operating System

---

## Event Bus (v1.2 — foundation only, not yet the primary communication path)

Introduced as infrastructure other modules CAN use, not a replacement for
the direct calls shown in Current Architecture above. Everything in
Current Architecture still works exactly as it did before this version —
the Event Bus coexists with it rather than routing through it.

**What exists:**
- `agent/events.py` — `Event` (generic envelope: type, payload, id,
  timestamp, source, metadata, trace_id) and `EventType` (the initial
  catalogue: `USER_COMMAND`, `PLAN_CREATED`, `TOOL_EXECUTED`,
  `TOOL_FAILED`, `TASK_COMPLETED`, `VOICE_STARTED`, `VOICE_STOPPED`,
  `BROWSER_OPENED`, `MEMORY_UPDATED`, `NOTIFICATION_ARRIVED`,
  `APPLICATION_FOCUSED`). Only `USER_COMMAND` is actually published
  anywhere yet — the rest are defined so future modules have a shared
  vocabulary to grow into, per the "define, don't force adoption" v1.2
  scope.
- `agent/event_bus.py` — `EventBus`: `subscribe()` / `unsubscribe()` /
  `publish()` (synchronous, immediate) / `publish_async()`
  (non-blocking, backed by a `queue.Queue` + background
  `threading.Thread`, not `asyncio` — see design note below) /
  `shutdown()` (graceful, drains the queue first). Process-wide singleton
  via `get_event_bus()`.
- `Event.trace_id` reuses the existing request-tracing system
  (`utils/trace.py`, from v1.1.1) rather than inventing a second
  correlation-id mechanism — an event published during a `/chat` request
  automatically carries that request's trace ID.

**Design decision — why threading, not asyncio:** most of this codebase
is fundamentally synchronous (`/chat` is a sync FastAPI route, run in
Starlette's thread pool). An asyncio-based queue would only work reliably
when called from inside a running event loop, which most of this code
isn't. `queue.Queue` is thread-safe by construction and callable
identically from sync or async code with no event-loop dependency —
trading "modern asyncio" for "actually fits the codebase as it is today."

**The one integration point wired up this version** (deliberately minimal
— see NON-GOALS below):

```
Planner.plan()
     |
     v  publish(Event(EventType.USER_COMMAND, ...))
Event Bus
     |
     v  (executor.py subscribed at import time)
Executor's _on_user_command() — currently just logs
```

`planner.py`'s `plan()` publishes a `USER_COMMAND` event as its first
line — a pure additive side effect; the function's signature, return
value, and existing logic are unchanged. `executor.py` subscribes to it
at module load time. The subscriber is deliberately inert beyond logging:
`execute_step()` / `execute_plan()` are still called directly by
`app/api/chat.py` exactly as before, unchanged. This proves the
publish → subscribe wiring works end-to-end without migrating any real
control flow onto it yet.

**Explicitly NOT done this version** (see the v1.2 brief's own NON-GOALS —
these are future versions, not oversights):
- World State, Capability Registry, Plugin System, Goal Engine, Knowledge
  Graph, Vision Engine, Multi-Agent System.
- No other module (Memory, Voice, Browser tools) publishes or subscribes
  to anything yet — only the one Planner → Executor path above.
- The event types beyond `USER_COMMAND` (`PLAN_CREATED`, `TOOL_EXECUTED`,
  etc.) are defined, not wired to anything — a future version's job.

---

## Future Architecture

Presentation Layer

↓

Core

↓

Event Bus

↓

World State

↓

Intelligence

↓

Memory

↓

Execution

↓

Connectors