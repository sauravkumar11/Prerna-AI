# Changelog

This file tracks notable fixes and changes to Prerna, one entry per change,
newest first. Each entry links the symptom (what was observed) to the root
cause (what was actually wrong) and the fix — not just "fixed a bug."

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