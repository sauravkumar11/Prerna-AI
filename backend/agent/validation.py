"""
Validation
==========
The "Validation" and "Permission Check" steps in:

    Planner -> Reasoning -> Validation -> Permission Check ->
    Tool Selection -> Execute -> Memory Update -> Response

`agent.reasoning` decides *which* tool/action matches the plan. This module
decides whether it's *safe* to actually run it: are all arguments present
and sane, and if it's destructive, has the user confirmed it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agent.registry import ToolAction


@dataclass
class ValidationResult:
    ok: bool
    missing_args: Optional[List[str]] = None
    needs_confirmation: bool = False
    error_message: Optional[str] = None


def validate_args(tool_action: ToolAction, args: Dict[str, Any]) -> List[str]:
    """Return the list of required args that are missing or empty."""
    missing = []
    for name in tool_action.required_args:
        value = args.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(name)
    return missing


def check_permission(tool_action: ToolAction, confirmed: bool) -> bool:
    """Return True if this action is allowed to run right now.

    Dangerous actions (shutdown, restart, delete, ...) require the caller
    to have already confirmed - see agent.executor for how the
    "requires_confirmation" round trip works with the frontend.
    """
    if not tool_action.dangerous:
        return True
    return confirmed


def validate(tool_action: ToolAction, args: Dict[str, Any], confirmed: bool) -> ValidationResult:
    missing = validate_args(tool_action, args)
    if missing:
        return ValidationResult(
            ok=False,
            missing_args=missing,
            error_message=f"I need more info: {', '.join(missing)}.",
        )

    if not check_permission(tool_action, confirmed):
        return ValidationResult(
            ok=False,
            needs_confirmation=True,
            error_message=(
                f"Are you sure? This will {tool_action.description.lower() or 'perform a destructive action'}. "
                "Say yes to confirm."
            ),
        )

    return ValidationResult(ok=True)
