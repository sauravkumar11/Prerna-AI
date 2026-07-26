"""
Executor
========
Runs a plan that has already passed through `agent.reasoning.reason()`.

Full pipeline: Planner -> Reason -> Validation -> Permission Check ->
Tool Selection -> Execute -> Verify -> Memory Update -> Response

`agent.planner.plan()` always returns a LIST of steps (even for a single
action) so compound commands like "open camera and click pictures" can run
as two real steps instead of the model being forced to squeeze everything
into one tool call. This file runs that list in order, stopping at the
first failure or confirmation request rather than plowing on regardless.

Verify: an action can optionally declare a `verify` function (see
agent.verification) that checks the action actually happened, not just that
the handler returned success — e.g. did the Camera window actually appear?
Only used for actions that opted in; everything else behaves exactly as
before.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from agent.reasoning import reason
from agent.registry import ToolResult, call_handler
from agent.validation import validate
from agent.verification import run_with_verification
from agent import session
from memory.memory_manager import log_activity


def execute_step(step: Dict[str, Any], confirmed: bool = False) -> ToolResult:
    """Execute exactly one {"tool": ..., "args": {...}} step."""

    outcome = reason(step)

    if outcome.tool_name == "chat":
        return ToolResult(True, "", data={"is_chat": True})

    if not outcome.ok or outcome.action is None:
        return ToolResult(False, outcome.error_message or "I couldn't do that.")

    tool_action = outcome.action
    args = step.get("args", {}) or {}

    validation = validate(tool_action, args, confirmed)
    if not validation.ok:
        data = (
            {
                "requires_confirmation": True,
                "tool": outcome.tool_name,
                "action": outcome.action_name,
                # The exact step that needs confirming — lets the confirmed
                # retry re-execute THIS directly instead of re-invoking the
                # (non-deterministic) planner on the same text a second time.
                "step": step,
            }
            if validation.needs_confirmation else None
        )
        return ToolResult(False, validation.error_message or "I couldn't do that.", data=data)

    result, verified = run_with_verification(
        call=lambda: call_handler(tool_action.handler, args),
        verify=tool_action.verify,
        args=args,
        max_retries=tool_action.max_retries,
    )

    if verified is False:
        # The tool itself reported success, but its verifier is confident
        # nothing actually changed after retrying — don't tell the user it
        # worked when we have a real signal it didn't.
        result = ToolResult(
            False,
            result.message + " I couldn't confirm this actually happened after trying again — worth checking manually.",
            data={**(result.data or {}), "verify_failed": True},
            speech=result.speech,
        )

    log_activity(
        f"{outcome.tool_name}.{outcome.action_name}",
        success=result.success,
        details=result.message,
    )

    session.update_from_action(outcome.tool_name, outcome.action_name, args, result)

    return result


def execute_plan(steps: List[Dict[str, Any]], confirmed: bool = False) -> ToolResult:
    """Execute a planner-produced plan: a list of one or more steps.

    Args:
        steps: [{"tool": str, "args": dict}, ...] as produced by agent.planner.plan
        confirmed: set True when the user has already confirmed a
            previously-flagged dangerous action (shutdown, delete, etc.)
    """

    if not steps:
        return ToolResult(True, "", data={"is_chat": True})

    # The common case: a single conversational step, no tool involved.
    if len(steps) == 1 and steps[0].get("tool") == "chat":
        return ToolResult(True, "", data={"is_chat": True})

    messages: List[str] = []
    executed: List[Tuple[str, bool]] = []

    real_steps = [s for s in steps if s.get("tool") != "chat"]
    is_multi_step = len(real_steps) > 1

    task_description = " then ".join(
        f"{s.get('tool')}.{(s.get('args') or {}).get('action', '')}".rstrip(".")
        for s in real_steps
    ) or "task"
    if is_multi_step:
        session.start_task(task_description, step_count=len(real_steps))

    for step in steps:
        if step.get("tool") == "chat":
            continue  # a stray chat step mixed into a multi-step plan; skip it

        result = execute_step(step, confirmed=confirmed)

        if result.data and result.data.get("requires_confirmation"):
            # Stop immediately and surface the confirmation prompt - don't
            # run later steps until the user has actually confirmed.
            return result

        if result.message:
            messages.append(result.message)
        executed.append((step.get("tool", "?"), result.success))

        if not result.success:
            break  # don't keep running steps after one has failed

    overall_success = all(ok for _, ok in executed) if executed else True
    if is_multi_step:
        session.finish_task(task_description, success=overall_success)

    if not messages:
        return ToolResult(True, "", data={"is_chat": True})

    return ToolResult(
        success=overall_success,
        message=" ".join(messages),
        data={"steps": executed},
    )