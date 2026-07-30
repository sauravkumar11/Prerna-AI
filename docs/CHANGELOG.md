# Changelog

This file tracks notable fixes and changes to Prerna, one entry per change,
newest first. Each entry links the symptom (what was observed) to the root
cause (what was actually wrong) and the fix — not just "fixed a bug."

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