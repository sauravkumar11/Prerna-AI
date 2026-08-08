# Changelog

This file tracks notable fixes and changes to Prerna, one entry per change,
newest first. Each entry links the symptom (what was observed) to the root
cause (what was actually wrong) and the fix — not just "fixed a bug."

---

## Prerna Core v1.2 — Event Bus Foundation

Scope, per the version brief: introduce Event Bus INFRASTRUCTURE only — no
migration of existing modules onto it, no World State / Plugin System /
Goal Engine / Knowledge Graph (explicit non-goals, deferred to future
versions). Backward compatibility was the hard constraint: nothing in
Planner, Executor, Memory, Voice, or Browser tools was rewritten.

### What was added

- **`agent/events.py`** — `Event` (generic envelope with id, timestamp,
  source, payload, metadata, and `trace_id` reusing v1.1.1's existing
  request-tracing system rather than a second correlation-id mechanism)
  and `EventType` (initial catalogue of 11 event types — defined for
  future use, not yet all wired to a publisher).
- **`agent/event_bus.py`** — `EventBus` with `subscribe()` /
  `unsubscribe()` / `publish()` (synchronous) / `publish_async()`
  (non-blocking) / `shutdown()` (graceful). Process-wide singleton via
  `get_event_bus()`.

**Design decision, stated explicitly per the brief's own instruction to
explain assumptions rather than make breaking changes:** the async queue
is built on `queue.Queue` + a background `threading.Thread`, not
`asyncio`. Most of this codebase (e.g. `/chat`, a sync FastAPI route run
in Starlette's thread pool) is fundamentally synchronous — an
asyncio-based queue would only work reliably from inside a running event
loop. `queue.Queue` is thread-safe by construction and works identically
from sync or async callers. Documented in full in `docs/ARCHITECTURE.md`.

### The one integration point (exactly as scoped — "Planner → publish
### (UserCommand) → Executor subscribes", no other module migrations)

- `agent/planner.py`'s `plan()` now publishes an `EventType.USER_COMMAND`
  event as its first line — a pure additive side effect. Signature,
  return value, and all existing logic are byte-for-byte unchanged.
- `agent/executor.py` subscribes to it at module load time. The
  subscriber (`_on_user_command`) is deliberately inert beyond a debug
  log line — `execute_step()` / `execute_plan()` are still called
  directly by `app/api/chat.py` exactly as before. This proves the
  publish → subscribe wiring works end-to-end without migrating any real
  control flow onto it.

**Verified end-to-end, not just each half in isolation:** imported the
real `executor.py` (registers exactly 1 subscriber), called the real,
unmodified `planner.plan()` with a fake model, and confirmed both that
the executor's subscriber genuinely received the event with the correct
payload AND that `plan()`'s actual return value was completely
unaffected.

### Tests

**`tests/test_event_bus.py` — 26 tests**, covering every item listed in
the version brief: subscribe, unsubscribe (including a safe no-op on an
unknown handler), synchronous publish, asynchronous publish, multiple
subscribers, exception handling (a failing handler is isolated and logged
— it does not stop other subscribers or propagate to the publisher),
event ordering (both synchronous subscription order and FIFO ordering
under the async queue), duplicate subscriptions (deliberately
deduplicated — see design note in `event_bus.py`), thread safety (20 real
concurrent `threading.Thread` workers hammering `publish_async()`, zero
lost events), and graceful queue shutdown (drains already-queued events
before stopping; the bus remains usable afterward — a fresh
`publish_async()` call restarts the worker rather than doing nothing
forever).

All pre-existing tests continue to pass — zero regressions, confirming
"preserve existing functionality."

### Explicitly deferred (per the version brief's own NON-GOALS — not
### oversights)

World State, Capability Registry, Plugin System, Goal Engine, Knowledge
Graph, Vision Engine, Multi-Agent System. Also: no module beyond Planner/
Executor publishes or subscribes to anything yet; the 10 event types
beyond `USER_COMMAND` are defined but not yet wired to any publisher —
both are intentional scope boundaries for a future version, not gaps in
this one.

---

## Prerna Core v1.1.2 — Reliability & Type Safety

Scope: only the four High-severity findings from the Architecture Review
that this version was created to close. No new features, no unrelated
refactoring, per the project's incremental-versioning rules.

### 1. `ToolResult` contract now enforced at construction time

**Root cause this closes:** the WhatsApp tuple/string bug (see entry
below) was possible because nothing prevented a tool wrapper from passing
the wrong type into `ToolResult.message`. That specific instance was
fixed already, but the *pattern* that allowed it was still open — any
other tool with the same mistake would fail the same way, deep inside
`execute_plan()`'s string join, far from the real cause.

**Fix:** `ToolResult.__post_init__` now validates `success` is a real
`bool`, `message` is a real `str`, and `speech` is a `str` or `None` —
raising a clear `TypeError` immediately, naming the actual problem.

**Why this can't introduce a new crash:** every tool handler already runs
inside `registry.safe()`'s try/except, which converts *any* exception
(including this new validation error) into a graceful failed `ToolResult`.
Verified directly: a handler reproducing the exact tuple bug now returns
a clean `ToolResult(success=False, message="... must be a str ...")`
instead of an uncaught exception three frames later.

**Tests:** `tests/test_registry.py` (11 tests) — normal usage unaffected,
every invalid-input case raises correctly, and the safe()-wrapper
absorption property is verified directly.

### 2. Defense-in-depth in `execute_plan()`'s message join

`" ".join(messages)` now coerces via `str(m)`. Redundant given fix #1
above under normal operation — deliberately kept as a second, independent
layer so this specific join can never crash even if something upstream
ever bypasses normal `ToolResult` construction.

### 3. Fixed unlocked race on `_model_failure_streak`

**Root cause:** `/chat` is a synchronous FastAPI route, which Starlette
runs in a thread pool — concurrent requests genuinely execute on
different OS threads. `_cooldown_until` mutations were already
lock-protected; `_model_failure_streak`'s read-modify-write increments
(added in an earlier session) were not.

**Fix:** added `_bump_failure_streak()` / `_reset_failure_streak()`
helpers, both using the same `self._lock` already protecting
`_cooldown_until`.

**Tests:** `tests/test_dependencies.py::test_model_failure_streak_thread_safe_under_real_concurrency`
— 20 genuine `threading.Thread` workers racing on the same counters.
Result: exactly 20/20/20 per model index, zero lost updates. (A failing
version of this test, run against the pre-fix code, would show counts
below 20 on at least one key — the classic signature of a lost update.)

**All 145 tests pass** (134 pre-existing/v1.1.1 + 11 new), zero
regressions, confirming "preserve existing behavior."

---

## Unreleased (post v1.1.1)

### Fixed: `ImportError` in YouTube's URL fallback path

**Symptom** (from a real production log):
```
ImportError: cannot import name '_find_chrome_exe' from 'tools.chrome_session'
```
Triggered whenever Selenium-based YouTube automation failed mid-session
(e.g. the automation Chrome window closed/crashed) and the code tried to
fall back to just opening a search URL directly in a browser.

**Root cause:** `tools/chrome_session.py` was rewritten earlier this
session to support multiple browser engines (Chrome and Edge, auto-
detected). That rewrite replaced the standalone `_find_chrome_exe()`
function with `_find_engine()` (returns an engine dict — name, display
name, and resolved exe path — rather than a bare path string).
`tools/youtube_tool.py`'s fallback function (`_url_fallback`) was never
updated to match and kept importing the now-removed function.

The system didn't fully break — `agent/goal_loop.py`'s existing retry
logic caught the exception, re-planned, and eventually succeeded a
different way — but that was masking a real bug behind ~10-15 seconds of
extra latency and a logged exception on every occurrence, not actually
working correctly.

**Fix:** `_url_fallback` now calls `_find_engine()` and reads
`engine["exe_path"]` / `engine["display_name"]`, matching the current
`chrome_session.py` API. No behavior change from the user's perspective —
the fallback still opens the search URL in whichever real browser engine
is installed — this just stops it from crashing first.

**Regression test:** `tests/test_youtube_fallback.py` (5 tests) — covers
the exact ImportError scenario, correct engine-exe launching, fallback to
`webbrowser.open()` when no engine is found, and survival of a failed
`Popen` call.

**Lesson for future refactors:** when a module's public function surface
changes (removed/renamed function, changed return shape), grep for every
caller across the whole codebase before considering the refactor done —
`grep -rn "_find_chrome_exe" --include=*.py .` would have caught this
immediately. This is exactly the kind of drift the Architecture Review's
Finding 7.1 (missing enforced contracts) was warning about; v1.1.2
(Reliability & Type Safety) is the planned fix for the underlying pattern,
not just this one instance of it.