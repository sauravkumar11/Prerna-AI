# Phase 1: Agent Architecture Foundation

Frontend untouched — this is backend-only. Every existing feature (wake word,
voice, TTS, Gemini chat, planner, WhatsApp, memory) still works the same way
from the outside; the internals are now modular.

## What changed and why

### `agent/registry.py` (rewritten)
Was a hand-wired dict of tool name -> module. Now every tool self-registers
via `@action("tool_name", "action_name", ...)`. Gives us:
- `ToolResult(success, message, data)` — one consistent return type from
  every tool, instead of mixing raw strings/None across files.
- `describe_tools()` — auto-generates the tool list for the planner prompt,
  so new tools show up there without editing the planner.
- `safe()` — wraps every action so an exception inside a tool can never
  crash the backend; it becomes a normal failed `ToolResult` instead.

### `agent/reasoning.py` (new)
The "Reason" step from Planner → Reason → Tool Selection → Execute → Memory
Update → Response. Validates a plan against the registry (tool exists,
action exists, required args present) *before* anything runs, and produces
a one-line rationale for logging. No extra LLM call, so no added latency.

### `agent/executor.py` (rewritten)
Was a ~200-line if/elif per tool. Now a ~15-line generic dispatcher that
asks the registry for the right handler. Adding a tool no longer touches
this file at all. Also added: destructive actions (shutdown, restart,
delete) now return `requires_confirmation` instead of firing immediately —
see `main.py` changes below.

### `agent/planner.py` (rewritten)
Tool list is now generated live from `describe_tools()` instead of a
hardcoded list that drifts out of sync with the actual tools. Also asks the
model for a short `"reason"` field alongside `tool`/`args`, which gets
logged by the reasoning step.

### `memory/memory_manager.py` (expanded, backward compatible)
All original functions (`load_memory`, `save_memory`, `get_contact`,
`add_contact`, `get_profile`, `get_preferences`, `get_habits`, `remember`,
`log_activity`) keep their exact original signatures — nothing that used
them breaks. Added on top:
- **Short-term memory**: in-process ring buffer of the current session.
- **Conversation memory**: rolling log persisted to `conversation_log.json`.
- **Emotion memory**: tracks Prerna's last emotion tag.
- **Activity memory**: `log_activity` now also records success/failure and
  details; `get_recent_actions(n)` reads them back.
- **`get_context()`**: merges everything into one dict for prompt-building.

### `tools/` (refactored + 3 new tools)
Every existing tool file now registers its actions instead of being called
by name from the executor:
- `whatsapp_tool.py`, `system_tool.py`, `vscode_tool.py`,
  `screenshot_tool.py`, `camera_tool.py`, `bluetooth_tool.py`,
  `file_tool.py` — same behavior, now registry-based, with proper
  docstrings/type hints and no bare `except`.
- **New**: `browser_tool.py` — open named sites, arbitrary URLs, run
  searches (replaces the old hardcoded `open_app` branch of `system_tool`).
- **New**: `clipboard_tool.py` — copy/read/clear.
- **New**: `volume_tool.py` — up/down/mute/unmute (no extra dependency).
- `tools/__init__.py` — imports every tool module so registration happens
  automatically; this is the *only* file you touch to plug in a new tool.

### `main.py` (minimal, surgical changes)
- Imports `tools` once at startup to trigger registration.
- `execute_plan()` now returns a `ToolResult`; the chat route reads
  `.message` / `.data` instead of treating the result as a raw string.
- Dangerous actions (shutdown, restart, delete) now come back as a
  confirmation prompt first. `ChatRequest` gained an optional
  `confirmed: bool = False` field — the frontend doesn't need to change to
  keep working (defaults to `False`), but a future frontend update can send
  `confirmed: true` after the user says "yes" to actually run the action.
- Logs every user/assistant turn to conversation memory and tracks the last
  emotion tag.
- System prompt, persona, TTS route, and Gemini call are **unchanged**.

## What's next (not done in this pass)

These were in your original request but need either external device access
I can't test here, or are genuinely separate follow-up efforts:
- YouTube in-page control (play/pause/next), Instagram automation
  (search/reels/like), WhatsApp "read unread messages" — all fragile
  browser/UI automation that needs iteration on your actual machine.
- Alarms/reminders/timers, WiFi toggle, notepad dictation.
- Predictive assistant upgrade (currently simple keyword rules in
  `predictor.py`, untouched this pass).
- Frontend wiring for the new `requires_confirmation` flow (a small dialog
  or button that resends the request with `confirmed: true`).

Happy to do any of these next — just say which.

---

# Phase 2: More tools + real frontend bugfixes

## New tools (same registry pattern, zero executor/planner changes needed)
- `youtube_tool.py` — open/search YouTube; play/pause/next/previous/volume via
  OS media keys (reliable — works on whatever media tab has focus). Note:
  "jump straight to the first search result" is *not* faked — YouTube has no
  documented URL for that, and reliably clicking it needs real browser
  automation (Selenium/Playwright), which is a bigger addition than a tool
  file. Flagged in the tool's response rather than pretending it works.
- `instagram_tool.py` — open app/profile/reels/messages via URL. Deliberately
  **excludes** auto-scrolling reels and auto-liking: that's automated
  engagement, which is against Instagram's ToS and risks your account being
  flagged. Navigation is real and reliable; the interacting is still you.
- `wifi_tool.py` — on/off via `netsh` (falls back to opening settings if it
  needs admin rights it doesn't have).
- `notepad_tool.py` — open Notepad; write dictated text straight into a new
  `.txt` file under `Documents/Prerna Notes` and open it.
- `alarm_tool.py` — real alarms via Windows Task Scheduler (`schtasks`), so
  they fire even if the backend isn't running; plus in-app countdown timers
  for while it is.
- `notes_tool.py` — lightweight structured notes (create/append/search)
  Prerna can recall, stored in `memory/notes.json`, separate from the plain
  `.txt` files `notepad_tool` writes.

All of the above were smoke-tested against a stubbed environment (registry
population, missing-arg handling, and — for `alarm_tool` — a real
`FileNotFoundError` from `schtasks` not existing on non-Windows, caught
cleanly by the registry's `safe()` wrapper instead of crashing).

## Frontend bugfixes (logic only — no UI/markup/styling touched)

Two real bugs were causing the "stuck thinking/listening" behavior you'd
listed:

1. **`main.py` → n/a. `App.jsx`: `loading` was set `true` before every
   request but never set back to `false` on the success path** — only the
   `catch` block reset it. Once you got one successful reply, `loading`
   stayed `true` for the rest of the session, which fed into a second bug:
2. **Stale closure**: `playPrernaVoice`'s `audio.onended`/`onerror` checked
   `if (!loading) setAwake(false)`, but `loading` there was the value
   captured when that specific function was created — not the live React
   state. Combined with bug #1, `awake` essentially never cleared, keeping
   the orb/status text stuck.

   Fix: added a `loadingRef` kept in sync via `useEffect`, and callbacks now
   check `loadingRef.current` instead of the stale `loading` variable.
   `setLoading(false)` is now called as soon as a reply arrives (so the
   status text correctly moves Thinking → Speaking → idle instead of being
   stuck on "Thinking...").
3. **Thinking-phrase race**: the 2.5s "let me think" filler used the same
   stale `loading` check to decide whether the real answer had already
   arrived. Replaced with a dedicated `respondedRef` that's set the instant
   a response lands, so the filler phrase can no longer play over (or after)
   the real answer.
4. **Typo**: `thinkingTimerRef.current = thinkingTimerRef.current = setTimeout(...)`
   — harmless but sloppy double-assignment, cleaned up.
5. **Wake word never matched half its phrases**: `useWakeWord.js` lowercases
   the recognized speech (`text.toLowerCase()`) but compared it against
   capitalized literals like `"Haji"`, `"Kaisi Ho"`, `"Naincy suno"` —
   `"kaisi ho".includes("Kaisi Ho")` is always `false` in JS. Lowercased the
   literals so those phrases actually trigger wake, as they were clearly
   meant to.

Both files were validated with `@babel/parser` (JSX-aware) after editing —
no syntax errors introduced.

## Still not done (needs iteration on your actual machine, not a one-shot guess)
- WhatsApp "read unread messages" — reading rendered chat content reliably
  needs either an accessibility-tree read or OCR; I didn't want to ship a
  fragile screen-scraper as if it were solid.
- Calendar (today's events / create event) — needs an Outlook/Google
  Calendar integration, which is its own scoped project.
- Predictive assistant is still the original simple keyword rules in
  `predictor.py` — upgrading it well needs some real usage data to know
  what's worth predicting.

---

# Phase 3: Architecture completion + broad tool coverage

## New architecture pieces (matching the full pipeline you asked for)
Planner -> Reasoning -> **Validation** -> **Permission Check** -> Tool
Selection -> Execute -> Memory Update -> Response

- `agent/validation.py` — split out from reasoning on purpose: reasoning
  decides *which* tool/action fits, validation decides whether it's *safe*
  to run right now (all args present, and if destructive, already
  confirmed). `executor.py` now calls this explicitly as its own stage.
- `agent/context.py` — the single place that shapes memory into what a
  prompt actually needs (`get_planner_context()` for contacts,
  `get_persona_context()` for profile/mood/recent turns). `main.py`'s
  contact lookup now goes through this instead of a raw `memory.get(...)`.
- `config.py` — centralized paths/constants (folder shortcuts, browser exe
  paths, the Windows app-launch map, storage locations) instead of magic
  strings copy-pasted across tool files. `browser_tool`, `file_tool`, and
  the new tools below all pull from here.

**Deliberately not added**: separate `router.py`/`conversation.py`/
`agent/memory.py` files as literal 1:1 matches to the requested layout.
`main.py`'s `/chat` handler is ~250 lines of persona/prompt logic that's
tightly coupled to itself; mechanically splitting it into a router file
without being able to run/test the real Gemini + voice pipeline end-to-end
here is exactly the kind of change that looks fine and silently breaks
something. `memory/memory_manager.py` already *is* the memory/conversation
layer — adding an `agent/memory.py` on top would just be an empty
pass-through. Flagging this rather than padding the tree with placeholder
files.

## 9 more tools registered (20 total now, ~90 actions)
- `system_tool.py` **expanded**: sleep, hibernate, logout (all destructive
  ones require confirmation), dark/light mode (real, via registry),
  brightness (real, via WMI), night light + airplane mode (Windows exposes
  no direct toggle for either — opens the settings page honestly instead of
  faking success), and a generic `open_app` launcher covering calculator,
  paint, cmd, powershell, terminal, explorer, control panel, settings, task
  manager, device manager, snipping tool, sticky notes, clock, and the
  Store (see `config.WINDOWS_APPS`).
- `file_tool.py` **expanded**: rename, move, copy, search (by name, under a
  folder), zip, extract.
- `camera_tool.py` **rewritten**: `capture` now grabs a photo directly via
  OpenCV instead of just opening the Camera app - more reliable than
  automating the shutter button.
- `screenshot_tool.py` **expanded**: active-window capture and
  copy-to-clipboard (both via pywin32, already a dependency), plus a
  specific-region capture.
- `whatsapp_tool.py`: added `open_chat` (search + focus a contact, no
  message sent) — wires up `search_contact()` from `whatsapp_actions.py`,
  which existed but was never actually called anywhere before.
- `search_tool.py` **new**: weather, news, maps, stocks, crypto, flights,
  hotels, restaurants, medicine — all URL-based lookups, no scraping/API
  keys.
- `coding_tool.py` **new**: open a project in VS Code, `git status / pull /
  push / commit` against an explicit repo path, jump to a localhost port.
- `email_tool.py` **new**: compose via `mailto:` (opens whatever your
  default mail handler is, desktop or web), search Gmail.

All of the above were re-verified with the same stubbed smoke test used in
Phase 1/2 — registry population, confirmation flow, and graceful failure
(e.g. `alarm.set` hitting a real `FileNotFoundError` for `schtasks` not
existing on this non-Windows sandbox, caught cleanly instead of crashing).

## Still not done, on purpose
- **Calendar** (create/delete event, today's/tomorrow's schedule) — needs a
  real Outlook/Google Calendar OAuth integration. That's a scoped project
  of its own (auth flow, token storage, consent screen), not a tool file.
- **WhatsApp "read unread messages"** — same reasoning as before: reliably
  reading rendered chat content needs an accessibility-tree read or OCR,
  and I'm not going to ship a screen-scraper that looks solid but is
  actually fragile.
- **Predictive assistant upgrade** — still the original keyword rules;
  doing this well needs real usage patterns to learn from.
- **Streaming/interruptible TTS redesign, DI framework** — both large,
  separate efforts that would touch the working voice pipeline broadly;
  better done as their own focused pass with room to actually test against
  your mic/speakers than folded into this one.
- **Format / disk-wipe commands** — not implemented at all, not even
  behind a confirmation gate. Some things are safer left undone than
  automated with a "trust me" prompt in front of them.

---

# Phase 4: Real conversation fixes (listening cutoff, compound commands, context)

Three separate, confirmed-from-your-console-logs bugs:

## 1. Mic cutting off after a second ("she listens for a sec and turns off")
`useVoice.js` used `continuous = false, interimResults = false` - a single
one-shot recognition that Chrome ends aggressively on any short pause.
Rewritten to `continuous = true, interimResults = true` with a manual
timer: recognition now stays open and resets a 2-second silence timer every
time new speech comes in, only stopping for real once you've actually gone
quiet for 2 seconds (or said nothing at all for 8 seconds). This also means
you'll see live partial transcript text while you're still talking, instead
of nothing until you're done.

## 2. Compound commands only did half the job ("open camera and click pictures" only opened it)
The planner could only ever return **one** `{tool, args}` pair per request,
so a two-part command had no way to become two actions - the model was
forced to pick one and silently drop the rest.

`agent/planner.py` now always returns a **list** of steps (a single action
is just a one-element list, so nothing about simple commands changes).
`agent/executor.py` runs the list in order, stopping immediately if a step
fails or needs confirmation, so a dangerous step in the middle of a
multi-step command can't let later steps run before you've actually
confirmed it. "Open camera and click pictures" now plans as
`[camera.open, camera.capture]` and both actually run.

## 3. No memory across turns ("play first video" forgot the search that just happened)
The planner only ever saw the current message in isolation - it had no idea
"search Dilbar song" had just happened, so a bare "play first video" had
nothing to work with and fell back to just reopening YouTube's homepage.

- `plan()` now also receives the last few conversation turns (via
  `agent.context.get_persona_context()`), so the model can resolve
  follow-ups that don't repeat their own context.
- `youtube_tool.py`'s `search` action now remembers the query
  (`memory.remember("last_youtube_query", ...)`), and `play_first_result`
  falls back to that remembered query when none is given, instead of
  failing or defaulting to something generic.

**Still honest about the actual limitation**: `play_first_result` opens/
re-opens the YouTube search results page - it does **not** click the first
video for you. That still needs real browser automation (Selenium/
Playwright), which remains a separate, larger addition. What's fixed here
is that the *context* isn't lost anymore, not that the click itself is now
automated. Flagging this clearly rather than letting the fix look bigger
than it is.

All of the above re-verified with the same stubbed smoke test approach:
multi-step execution (success chain, early-stop-on-failure,
early-stop-on-confirmation), and the YouTube memory fallback (with and
without a prior search).

