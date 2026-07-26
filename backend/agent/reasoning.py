"""
Reasoning
=========
The step between "planner decided what to do" and "executor does it".

Flow: Planner -> Reason -> Tool Selection -> Execute -> Memory Update -> Response

This module doesn't call the LLM again (that would add latency to every
action). Instead it validates the plan against what's actually registered,
fills in cheap defaults, and produces a short human-readable rationale that
gets logged - so you can see *why* Prerna chose an action, not just *what*
she chose.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from agent.registry import ToolAction, get_tool


@dataclass
class ReasoningOutcome:
    ok: bool
    rationale: str
    tool_name: Optional[str] = None
    action_name: Optional[str] = None
    action: Optional[ToolAction] = None
    error_message: Optional[str] = None


def reason(plan: Dict[str, Any]) -> ReasoningOutcome:
    """Validate a planner output before it's executed.

    Checks (in order):
      1. Does the tool exist in the registry?
      2. Does the requested action exist on that tool?
      3. Are all required arguments present?
    """

    tool_name = plan.get("tool")
    args = plan.get("args", {}) or {}
    action_name = args.get("action", "default")

    if not tool_name or tool_name == "chat":
        return ReasoningOutcome(
            ok=True,
            rationale="No tool needed; this is conversational.",
            tool_name="chat",
        )

    tool = get_tool(tool_name)
    if tool is None:
        return ReasoningOutcome(
            ok=False,
            rationale=f"Planner picked unknown tool '{tool_name}'.",
            error_message=f"I don't have a '{tool_name}' tool yet.",
        )

    tool_action = tool.actions.get(action_name) or tool.actions.get("default")
    if tool_action is None:
        return ReasoningOutcome(
            ok=False,
            rationale=f"Tool '{tool_name}' has no action '{action_name}'.",
            error_message=f"I don't know how to '{action_name}' with {tool_name} yet.",
        )

    missing = [a for a in tool_action.required_args if a not in args]
    if missing:
        # Reasoning still flags this for its rationale/log, but the actual
        # gate is agent.validation.validate() (kept separate on purpose so
        # "what tool fits" and "is it safe/complete to run" don't get mixed).
        return ReasoningOutcome(
            ok=True,
            rationale=f"Chose {tool_name}.{tool_action.name}, but args look incomplete: missing {missing}.",
            tool_name=tool_name,
            action_name=tool_action.name,
            action=tool_action,
        )

    rationale = f"Chose {tool_name}.{tool_action.name} to satisfy the request."
    if tool_action.dangerous:
        rationale += " This action is destructive, so it needs confirmation first."

    return ReasoningOutcome(
        ok=True,
        rationale=rationale,
        tool_name=tool_name,
        action_name=tool_action.name,
        action=tool_action,
    )
