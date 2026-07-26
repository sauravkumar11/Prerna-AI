"""
Goal Loop
=========
The real, buildable version of "don't execute one tool and stop" — a
bounded Observe -> Think -> Act -> Verify -> Recover -> Continue loop built
on infrastructure that already exists (agent.planner, agent.executor,
agent.verification's per-action verify functions), rather than a full
desktop-vision rewrite that can't be tested or trusted without a live
Windows machine + WhatsApp instance to validate against.

What this actually does:
  1. Plan and execute the request exactly as before (attempt 1 — same
     latency, same behavior as the old direct plan()+execute_plan() call
     for every request that succeeds on the first try, which is most of
     them).
  2. If that fails — a real failure, not "is_chat" and not "needs
     confirmation" — feed the failure message back to the planner as fresh
     context and ask for a new plan, up to `max_iterations` attempts. This
     is where per-action `verify=` functions (agent.verification) actually
     pay off: a step whose verifier caught a false-success gets a genuinely
     different retry, informed by *why* it failed, not a blind repeat.
  3. Stop conditions, checked every iteration: success, a confirmation
     request (NEVER auto-retried past — a safety gate stays a safety gate
     regardless of how many attempts are left), or `max_iterations`
     exhausted. Exhaustion returns the LAST attempt's honest failure
     message — never a fabricated success.

What this deliberately does NOT do (yet): no screen vision/OCR, no
per-app UI taxonomy (e.g. WhatsApp's business-vs-personal-vs-group chat
layouts), no click-coordinate self-correction. Recovery here works at the
level tools already expose (retry a different action, adjust an argument,
try a different tool) — it's bounded by what the planner can infer from a
text failure message, not by what it can literally see on screen. Real
per-app vision would be the natural next layer on top of this loop, not a
replacement for it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent.executor import execute_plan
from agent.planner import plan
from agent.registry import ToolResult
from utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_MAX_ITERATIONS = 3


def run_goal(
    user_message: str,
    model,
    contacts: Dict[str, Any],
    recent_turns: List[Dict[str, Any]],
    active_window: Optional[Dict[str, Any]],
    session_state: Optional[Dict[str, Any]],
    confirmed: bool = False,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> ToolResult:
    """Plan + execute, retrying with re-planning on genuine failure.

    Returns the same ToolResult shape execute_plan() always returned, so
    chat.py's handling of the result (is_chat / requires_confirmation /
    success) needs no changes beyond calling this instead of the old
    plan()+execute_plan() pair.
    """
    last_result: Optional[ToolResult] = None
    failure_notes: List[str] = []

    for attempt in range(1, max_iterations + 1):
        message_for_planner = user_message
        if failure_notes:
            message_for_planner = (
                f"{user_message}\n\n"
                f"[Internal retry context — attempt {attempt} of {max_iterations}. "
                f"Earlier attempt(s) at this same request failed: "
                f"{' | '.join(failure_notes)}. Try a different action, tool, or "
                f"argument that avoids the same failure — don't just repeat it.]"
            )

        steps = plan(message_for_planner, model, contacts, recent_turns, active_window, session_state)
        logger.debug("goal_loop attempt %d/%d plan: %s", attempt, max_iterations, steps)

        result = execute_plan(steps, confirmed=confirmed)
        last_result = result

        is_chat = bool(result.data and result.data.get("is_chat"))
        needs_confirmation = bool(result.data and result.data.get("requires_confirmation"))

        # Stop conditions that are NEVER retried, regardless of attempts left:
        #   - pure conversation (nothing to retry)
        #   - a confirmation gate (retrying past this would mean auto-confirming
        #     a dangerous action, which is exactly the safety property that
        #     gate exists to prevent — a bounded loop must never override it)
        #   - genuine success
        if is_chat or needs_confirmation or result.success:
            if attempt > 1:
                logger.info(
                    "goal_loop recovered after %d attempt(s) for: %r",
                    attempt, user_message,
                )
            return result

        failure_notes.append((result.message or "unknown failure")[:160])
        logger.info(
            "goal_loop attempt %d/%d failed for %r: %s",
            attempt, max_iterations, user_message, result.message,
        )

    # Exhausted every attempt — return the LAST real result as-is. Never
    # synthesize a success message here; an honest final failure (with
    # whatever recovery was actually attempted already logged above) is
    # the whole point of this module existing.
    return last_result
