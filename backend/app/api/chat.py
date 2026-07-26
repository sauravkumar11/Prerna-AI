"""
Chat router  —  POST /chat
==========================
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException

from agent.planner import plan
from agent.executor import execute_plan, execute_step
from agent.goal_loop import run_goal
from agent.predictor import predict
from agent.context import get_planner_context, get_persona_context
from agent.intent_gate import looks_like_tool_request
from agent.instant_engine import match as instant_match
from app.models import ChatRequest
from app.persona import (
    build_chat_prompt,
    matches_sleep_intent,
    sleep_response,
    EMOTION_TAGS,
)
from config.settings import GEMINI_CHAT_TEMPERATURE
from memory import mood_state
from memory.memory_manager import (
    load_memory,
    add_conversation_turn,
    set_last_emotion,
)
from utils.logger import get_logger
from utils.trace import new_trace

logger = get_logger(__name__)
router = APIRouter()

# Same whitelist the frontend's EMOTION_REGEX enforces. Previously this was
# `\[(\w+)\]` — any bracketed word — so a Gemini reply with an off-list tag
# (typo or an invented mood) would match here, get stored as the "last
# emotion", but silently fail the frontend's stricter regex and leak into
# the displayed chat bubble as raw "[TAG] ..." text instead of being
# stripped. Keeping both regexes in sync fixes that.
_EMOTION_NAMES = "|".join(tag.strip("[]") for tag in EMOTION_TAGS)
EMOTION_REGEX = re.compile(rf"^\[({_EMOTION_NAMES})\]", re.IGNORECASE)

# Gemini is asked to append `MEMORY: <note>` on its own line when something
# emotionally significant came up — this pulls it out of the reply before
# it's shown/spoken, and feeds it into persistent mood/event memory.
_MEMORY_LINE_REGEX = re.compile(r"(?im)^\s*MEMORY:\s*(.+)\s*$")


def _get_model():
    from app.dependencies import get_gemini_model
    return get_gemini_model()


def _strip_memory_line(reply: str) -> tuple[str, str | None]:
    match = _MEMORY_LINE_REGEX.search(reply)
    if not match:
        return reply, None
    note = match.group(1).strip()
    cleaned = _MEMORY_LINE_REGEX.sub("", reply).strip()
    return cleaned, note


@router.post("/chat")
def chat(request: ChatRequest):
    user_message = request.message.strip()

    # Everything in this request — including every logger.info() call in
    # every module it touches (planner, executor, dependencies, tools,
    # ...), none of which needed to change — now carries this same Trace
    # ID automatically via contextvars. See utils/trace.py + utils/logger.py.
    with new_trace(user_message[:60]) as trace:
        try:
            lower_message = user_message.lower()

            logger.info("Chat: %s", user_message)

            open_events = mood_state.get_open_events()

            # ── Going-to-sleep shortcut (zero Gemini quota, intent-detected —
            # not a literal hardcoded phrase match) ─────────────────────────
            if matches_sleep_intent(lower_message):
                reply = sleep_response(open_events)
                add_conversation_turn("user", user_message)
                add_conversation_turn("assistant", reply)
                set_last_emotion("CARING")
                mood_state.update_from_tag("CARING")
                return {"response": reply, "speech": reply}

            # ── Tier 0: Instant Engine — zero-LLM, zero-context-loading fast
            # path for unambiguous commands (volume, lock, screenshot, brightness
            # with a plain number, opening a known app, ...). Checked before ANY
            # memory/context loading or Gemini call — this is what actually
            # makes "volume up" feel instant instead of waiting on a full
            # pipeline built for compound, ambiguous requests. A miss here is
            # always safe: falls through to the normal pipeline below exactly
            # as if this check didn't exist. Skipped during a confirmation
            # retry (request.confirmed_step), which is handled explicitly below.
            if not request.confirmed_step:
                with trace.stage("tier0_check"):
                    instant_step = instant_match(user_message)
                if instant_step is not None:
                    add_conversation_turn("user", user_message)
                    with trace.stage("tier0_execute"):
                        tool_result = execute_plan([instant_step], confirmed=request.confirmed)

                    if tool_result.data and tool_result.data.get("requires_confirmation"):
                        reply = f"[CALM] {tool_result.message}"
                        speech = tool_result.speech or tool_result.message
                        add_conversation_turn("assistant", reply)
                        return {
                            "response": reply,
                            "speech": speech,
                            "requires_confirmation": True,
                            "pending_step": tool_result.data.get("step"),
                        }

                    reply = f"[CALM] {tool_result.message}"
                    speech = tool_result.speech or tool_result.message
                    set_last_emotion("CALM")
                    add_conversation_turn("assistant", reply)
                    return {"response": reply, "speech": speech}

            # ── Memory ────────────────────────────────────────────────────────
            with trace.stage("context_load"):
                memory = load_memory()
                profile      = memory.get("profile", {})
                habits       = memory.get("habits", {})
                preferences  = memory.get("preferences", {})
                planner_ctx   = get_planner_context()
                contacts      = planner_ctx["contacts"]
                active_window = planner_ctx["active_window"]
                session_state = planner_ctx["session"]
                persona_ctx   = get_persona_context()
                recent_turns  = persona_ctx["recent_turns"]

                # ── Predictive suggestions ────────────────────────────────────
                suggestions    = predict(user_message, memory)
                prediction_text = suggestions[0] if suggestions else ""

                model = _get_model()

            # ── Intent gate: skip the planner's Gemini call entirely for
            # messages that don't plausibly need a tool (saves ~half the
            # Gemini calls for ordinary conversation, which is most of usage
            # and where quota exhaustion hits hardest) ─────────────────────
            add_conversation_turn("user", user_message)

            if request.confirmed_step:
                # Deterministic confirmation retry: re-execute the EXACT step
                # that asked for confirmation, instead of resending the
                # original text through the planner again. Two Gemini planning
                # calls for the literal same message aren't guaranteed to agree
                # — this is what actually fixes a dangerous action silently
                # rerouting to plain chat several turns after the user already
                # said yes (observed in practice with whatsapp.block).
                with trace.stage("confirmed_step_execute"):
                    tool_result = execute_step(request.confirmed_step, confirmed=True)
            elif looks_like_tool_request(user_message):
                # goal_loop: plan + execute, and on a genuine failure (not
                # chat, not a confirmation gate), re-plan with that failure as
                # context and retry — bounded, and identical latency/behavior
                # to the old direct plan()+execute_plan() call whenever the
                # first attempt already succeeds (the common case).
                with trace.stage("planner_and_execute"):
                    tool_result = run_goal(
                        user_message, model, contacts, recent_turns, active_window, session_state,
                        confirmed=request.confirmed,
                    )
            else:
                with trace.stage("chat_plan_step"):
                    tool_result = execute_plan(
                        [{"tool": "chat", "args": {}, "reason": "No tool vocabulary detected — pure conversation."}],
                        confirmed=request.confirmed,
                    )
            is_chat = bool(tool_result.data and tool_result.data.get("is_chat"))

            # Tool executed — return immediately, NO second Gemini call needed
            if not is_chat:
                if tool_result.data and tool_result.data.get("requires_confirmation"):
                    reply = f"[CALM] {tool_result.message}"
                    speech = tool_result.speech or tool_result.message
                    add_conversation_turn("assistant", reply)
                    return {
                        "response": reply,
                        "speech": speech,
                        "requires_confirmation": True,
                        # The frontend stores this and sends it back verbatim as
                        # confirmed_step if the user says yes — see above.
                        "pending_step": tool_result.data.get("step"),
                    }

                reply = f"[CALM] {tool_result.message}"
                speech = tool_result.speech or tool_result.message
                set_last_emotion("CALM")
                add_conversation_turn("assistant", reply)
                return {"response": reply, "speech": speech}

            # ── Pure conversation — 1 Gemini call ─────────────────────────────
            with trace.stage("prompt_build"):
                prompt = build_chat_prompt(
                    user_message=user_message,
                    profile=profile,
                    contacts=contacts,
                    habits=habits,
                    preferences=preferences,
                    history=request.history,
                    mood_description=persona_ctx["mood_description"],
                    open_events=open_events,
                )

            # generate_content NEVER raises on quota — manager handles it
            with trace.stage("gemini_chat_call"):
                response = model.generate_content(
                    prompt,
                    generation_config={"temperature": GEMINI_CHAT_TEMPERATURE},
                )

            reply = (
                response.text.strip()
                if response.text
                else "[CALM] I'm sorry Saurav, something went wrong."
            )

            reply, memory_note = _strip_memory_line(reply)
            speech = reply  # capture before appending the text-only suggestion tail

            if prediction_text:
                reply += f"\n\n[Suggestion] {prediction_text}"

            emotion_match = EMOTION_REGEX.match(reply)
            if emotion_match:
                tag = emotion_match.group(1).upper()
                set_last_emotion(tag)
                mood_state.update_from_tag(tag)

            if memory_note:
                mood_state.remember_event(memory_note)

            add_conversation_turn("assistant", reply)
            return {"response": reply, "speech": speech}

        except Exception as exc:
            logger.exception("Chat error: %s", exc)
            # Return a friendly response instead of a 500 that crashes the frontend
            friendly = "[CALM] Sorry Saurav, something went wrong on my end. Try again."
            return {"response": friendly, "speech": friendly}
        finally:
            logger.info(trace.summary())