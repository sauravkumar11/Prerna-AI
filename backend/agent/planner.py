"""
Planner
=======
Turns Saurav's message into one or more structured steps: which tool, which
action, which arguments, per step. The tool/action list is generated live
from the registry (agent.registry.describe_tools) so new tools show up here
automatically - nothing to hardcode when tools/ grows.

Contract: plan() always returns a LIST of step dicts, even for a single
action - [{"tool": ..., "args": {...}, "reason": ...}, ...]. This is what
lets compound commands ("open camera and click pictures") run as two real
steps instead of the model being forced to pick just one.

v1.2: publishes an EventType.USER_COMMAND event via the Event Bus the
moment a message enters planning — the one deliberate, minimal integration
point for this version (see docs/ARCHITECTURE.md). This is a pure
additive side effect: it does not change plan()'s signature, return
value, or existing control flow in any way. If the Event Bus has zero
subscribers (as it will until executor.py's subscription, or in any
environment that doesn't import that module), this publish is a fast,
harmless no-op.
"""

from __future__ import annotations

import json
from utils.logger import get_logger
from typing import Any, Dict, List

from agent.registry import describe_tools
from agent.event_bus import get_event_bus
from agent.events import Event, EventType
from config.settings import GEMINI_PLAN_TEMPERATURE

logger = get_logger(__name__)

FEW_SHOT_EXAMPLES = """
User: Papa ko call kar do
[{"tool":"whatsapp","args":{"action":"voice_call","contact":"Papaji"},"reason":"Voice call to a known contact."}]

User: Varsha Di ko hi bhej do
[{"tool":"whatsapp","args":{"action":"send_message","contact":"Varsha Di","message":"Hi"},"reason":"Send WhatsApp message."}]

User: Open WhatsApp
[{"tool":"whatsapp","args":{"action":"open"},"reason":"Open WhatsApp Desktop."}]

User: Open camera and click pictures
[
  {"tool":"camera","args":{"action":"open"},"reason":"Open Camera app first."},
  {"tool":"camera","args":{"action":"take_picture"},"reason":"Then auto-click the shutter."}
]

User: Screenshot le lo
[{"tool":"screenshot","args":{"action":"default"},"reason":"Full screen screenshot."}]

User: VS Code kholo
[{"tool":"vscode","args":{"action":"open"},"reason":"Open VS Code editor."}]

User: Bluetooth on karo
[{"tool":"bluetooth","args":{"action":"on"},"reason":"Turn Bluetooth on."}]

User: YouTube pe Dilbar song chalao
[{"tool":"youtube","args":{"action":"search","query":"Dilbar song"},"reason":"Search YouTube and auto-play the first result."}]

User: Open YouTube and play Dilbar song
[{"tool":"youtube","args":{"action":"search","query":"Dilbar song"},"reason":"youtube.search now auto-plays the first result via browser automation."}]

User: Open YouTube and play dilbar song without asking, simply play the first song
[{"tool":"youtube","args":{"action":"search","query":"Dilbar song"},"reason":"youtube.search auto-clicks and plays the first result directly."}]

User: Play Dilbar song
[{"tool":"youtube","args":{"action":"search","query":"Dilbar song"},"reason":"Play song on YouTube - search auto-plays first result."}]

User: Play first video
[{"tool":"youtube","args":{"action":"play_first_result"},"reason":"Play first result from last YouTube search."}]

User: Skip the ad
[{"tool":"youtube","args":{"action":"skip_ad"},"reason":"Skip the current YouTube ad."}]

User: Pause the video
[{"tool":"youtube","args":{"action":"play_pause"},"reason":"Pause YouTube playback."}]

User: Pause it
[{"tool":"youtube","args":{"action":"play_pause"},"reason":"Session state shows YouTube is the current app with a song playing - 'it' refers to that."}]

User: Reply okay to her
[{"tool":"whatsapp","args":{"action":"send_message","contact":"<whatsapp_chat from session state>","message":"Okay"},"reason":"Session state's open WhatsApp chat tells us who 'her' is."}]

User: Next video
[{"tool":"youtube","args":{"action":"next"},"reason":"Skip to next YouTube video."}]

User: Open notepad
[{"tool":"notepad","args":{"action":"open"},"reason":"User just wants notepad open, no dictation specified."}]

User: Open notepad and write what I'm saying
[{"tool":"notepad","args":{"action":"write","text":""},"reason":"User wants to dictate - open notepad ready for input. Text will come from next voice input."}]

User: Open notepad and write a letter to my friend
[{"tool":"notepad","args":{"action":"write","text":"Dear Friend,"},"reason":"User wants to dictate a letter - start with a greeting."}]

User: Notepad mein likho - aaj ka din bahut acha tha
[{"tool":"notepad","args":{"action":"write","text":"Aaj ka din bahut acha tha"},"reason":"User dictated text to write in notepad."}]

User: Calculator kholo
[{"tool":"system","args":{"action":"open_app","app":"calculator"},"reason":"Open Windows calculator."}]

User: Mumbai ka weather batao
[{"tool":"search","args":{"action":"weather","place":"Mumbai"},"reason":"Weather search."}]

User: Laptop shutdown kar do
[{"tool":"system","args":{"action":"shutdown"},"reason":"Shut down the computer. Dangerous — needs confirmation."}]

User: Volume up karo
[{"tool":"volume","args":{"action":"up"},"reason":"Increase system volume."}]

User: Note banao — meeting at 5pm
[{"tool":"notes","args":{"action":"create","content":"meeting at 5pm"},"reason":"Create a quick note."}]

User: 7 baje alarm lagao
[{"tool":"alarm","args":{"action":"set","time":"07:00"},"reason":"Set alarm at 7:00 AM."}]

User: Chrome mein google kholo aur AI search karo
[
  {"tool":"browser","args":{"action":"open_site","site":"google"},"reason":"Open Google first."},
  {"tool":"browser","args":{"action":"search","query":"AI"},"reason":"Then search for AI."}
]

User: Main sone ja raha hu
[{"tool":"chat","args":{},"reason":"Conversational, no action needed."}]

User: Open the picture
[{"tool":"file","args":{"action":"open","path":"<session state's 'Last photo saved at' value>"},"reason":"Session state has the real saved photo path — use it directly, never guess a folder name."}]

User: Block Lenskart
[{"tool":"whatsapp","args":{"action":"block","contact":"Lenskart"},"reason":"whatsapp.block is a registered action — call it directly, regardless of any doubt about whether the UI automation will succeed. The tool itself honestly reports success or failure; don't pre-empt that by rerouting to chat."}]
""".strip()


def _format_recent_turns(recent_turns: List[Dict[str, Any]]) -> str:
    if not recent_turns:
        return "(none yet)"
    lines = []
    for turn in recent_turns:
        role = turn.get("role", "?")
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        lines.append(f"{role}: {content}")
    return "\n".join(lines) or "(none yet)"


def _format_active_window(active_window: Dict[str, Any]) -> str:
    if not active_window or not active_window.get("title"):
        return "(unknown — window info unavailable right now)"
    return f"{active_window['title']} (process: {active_window.get('process', '?')})"


def _format_session_state(session_state: Dict[str, Any] | None) -> str:
    if not session_state:
        return "(nothing tracked yet this session)"

    lines = []
    if session_state.get("current_app"):
        lines.append(f"Current app in use: {session_state['current_app']}")
    if session_state.get("song"):
        lines.append(f"Currently playing/last played: {session_state['song']}")
    if session_state.get("whatsapp_chat"):
        lines.append(f"Open WhatsApp chat: {session_state['whatsapp_chat']}")
    if session_state.get("browser_tab"):
        lines.append(f"Last browser tab/site: {session_state['browser_tab']}")
    if session_state.get("folder"):
        lines.append(f"Last folder/project touched: {session_state['folder']}")
    if session_state.get("document"):
        lines.append(f"Last file touched: {session_state['document']}")
    if session_state.get("last_screenshot"):
        lines.append(f"Last screenshot saved at: {session_state['last_screenshot']}")
    if session_state.get("last_photo"):
        lines.append(f"Last photo saved at: {session_state['last_photo']}")
    if session_state.get("current_task"):
        lines.append(f"In-progress multi-step task: {session_state['current_task']}")

    return "\n".join(lines) if lines else "(nothing tracked yet this session)"


def _build_prompt(
    user_message: str,
    contacts: Dict[str, Any],
    recent_turns: List[Dict[str, Any]],
    active_window: Dict[str, Any] | None = None,
    session_state: Dict[str, Any] | None = None,
) -> str:
    tools_description = describe_tools()

    return f"""
You are an AI planner.

Your job is to understand Saurav's intent and decide what action(s) should be taken.

Available tools and actions:
{tools_description}
- chat: no tool needed, this is just a conversation
- window: use "window"/"get_active" if Saurav asks what's on screen / which
  window is open / what he's currently doing on the laptop.

Known contacts:
{contacts}

Currently focused window on screen (use this for context, e.g. resolving
"close this" or "what am I looking at" — don't mention it unless relevant):
{_format_active_window(active_window or {})}

What Prerna is currently doing (use this to resolve bare follow-ups like
"pause it", "next one", "reply okay to her", "increase the volume", "add
another file there" — these refer to THIS, not the conversation text):
{_format_session_state(session_state)}

Recent conversation (most recent last - use this to resolve follow-ups like
"play first video" or "do that again" that don't repeat earlier context):
{_format_recent_turns(recent_turns)}

User message:
"{user_message}"

Return ONLY a valid JSON array, even for a single action:
[
    {{"tool": "", "args": {{}}, "reason": ""}}
]

If the request has multiple distinct actions (e.g. "open camera and click
pictures"), return one entry per action, in order. If it's a single action,
return a one-element array. "reason" is one short sentence explaining why
you picked that tool/action.

Examples:

{FEW_SHOT_EXAMPLES}

Rules:
- Return ONLY the JSON array. Never use markdown. Never explain outside the JSON.
- Infer intent naturally and fix speech recognition mistakes.
- Use known contacts when a name is mentioned.
- Use the current session state to resolve bare follow-ups ("it", "her",
  "that folder") when they clearly refer to what's tracked there.
- Use the recent conversation to resolve follow-ups that lack their own context.
- If intent is unclear but conversational, return a single-element array with tool "chat".
- Only use action names that were listed for that tool above.
- Don't invent extra steps beyond what the user actually asked for.

SMART INTENT RULES (very important):
- "play X on YouTube" or "open YouTube and play X" → use youtube.search with query X. Never say you can't play it.
- "open notepad and write/type/note what I say/dictate" → use notepad.write. Extract any dictated text as the content.
- "open notepad and write [text]" → notepad.write with that text as content.
- If user says "play [song name]" anywhere, infer they want YouTube search for that song.
- If user says "write/type/note/dictate" with notepad, infer notepad.write action.
- Always pick the most helpful interpretation — if "play Dilbar song" can mean YouTube, use YouTube.
- Never respond with chat when a clear tool action is implied.
- CRITICAL: if a tool/action in the list above matches the request, you MUST
  output that tool call — even if you personally doubt a UI-automation-based
  action will succeed. Your own belief about whether something "can really
  be done" is irrelevant here; tool availability in the list above is the
  ONLY thing that decides tool-vs-chat. The tool's own code (not you) is
  responsible for reporting whether it actually worked, including an honest
  failure message if it didn't — that already happens correctly downstream.
  Silently rerouting a matched action to "chat" and explaining in
  conversation why you "can't do it directly" produces a WORSE outcome than
  calling the real tool and letting its real result (success OR an honest
  failure) come back — never do this.
- For "open that/the picture/photo/screenshot" style follow-ups, use the
  exact path from session state's "Last photo saved at" / "Last screenshot
  saved at" line if present — never invent or guess a path/folder name
  (e.g. never pass just "Pictures" or "Camera Roll" as a file path).
"""


def plan(
    user_message: str,
    model,
    contacts: Dict[str, Any],
    recent_turns: List[Dict[str, Any]] = None,
    active_window: Dict[str, Any] = None,
    session_state: Dict[str, Any] = None,
) -> List[Dict[str, Any]]:
    # v1.2 Event Bus: pure additive side effect, no impact on control flow
    # or return value below. See module docstring.
    get_event_bus().publish(
        Event(EventType.USER_COMMAND, payload={"message": user_message}, source="planner")
    )

    prompt = _build_prompt(user_message, contacts, recent_turns or [], active_window, session_state)

    response = model.generate_content(prompt, generation_config={"temperature": GEMINI_PLAN_TEMPERATURE})

    raw = (response.text or "").strip()
    logger.debug("Planner raw output: %s", raw)

    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        parsed = json.loads(raw)
    except Exception as exc:
        logger.warning("Planner parse error: %s | raw=%r", exc, raw)
        return [{"tool": "chat", "args": {}, "reason": "Failed to parse planner output; defaulting to chat."}]

    # Backward/forward compatible: accept either a bare object or a list.
    if isinstance(parsed, dict):
        parsed = [parsed]

    if not isinstance(parsed, list) or not parsed:
        return [{"tool": "chat", "args": {}, "reason": "Planner returned an unexpected shape; defaulting to chat."}]

    steps = []
    for step in parsed:
        if not isinstance(step, dict):
            continue
        step.setdefault("args", {})
        step.setdefault("reason", "")
        steps.append(step)

    return steps or [{"tool": "chat", "args": {}, "reason": "No usable steps parsed; defaulting to chat."}]