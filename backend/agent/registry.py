"""
Tool Registry
=============
Central, self-assembling registry for every automation tool Prerna can use.

Instead of a giant if/elif chain in the executor, each tool module declares
its own actions with the `@action(...)` decorator. Importing `tools`
(see tools/__init__.py) causes every tool to register itself here.

This is the foundation the rest of the agent (planner, executor, reasoning)
is built on:

    planner   -> reads describe_tools() to know what's available
    executor  -> looks up plan["tool"] / args["action"] in get_registry()
    reasoning -> validates a plan against the registry before executing
"""

from __future__ import annotations

import functools
import inspect
from utils.logger import get_logger
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = get_logger(__name__)


@dataclass
class ToolResult:
    """Standard return value for every tool action.

    Every tool handler should return one of these (or a plain value / string,
    which `safe()` will wrap automatically). This keeps the executor and the
    API layer decoupled from the internals of any one tool.

    `speech` is an optional short, TTS-friendly version of the result —
    e.g. "Playing Dilbar." instead of reading out a full YouTube title with
    every featured artist, or "Screenshot saved." instead of reading a full
    Windows file path aloud. When omitted, `message` is used for speech too
    (existing behaviour, fully backward compatible).
    """

    success: bool
    message: str
    data: Optional[Any] = None
    speech: Optional[str] = None

    def __str__(self) -> str:  # convenient for f-strings / legacy callers
        return self.message


@dataclass
class ToolAction:
    name: str
    handler: Callable[..., "ToolResult"]
    description: str = ""
    required_args: List[str] = field(default_factory=list)
    dangerous: bool = False  # requires user confirmation (delete/shutdown/etc.)
    verify: Optional[Callable] = None
    max_retries: int = 0
@dataclass
class Tool:
    name: str
    description: str = ""
    actions: Dict[str, ToolAction] = field(default_factory=dict)

    def add_action(self, tool_action: ToolAction) -> None:
        self.actions[tool_action.name] = tool_action


# The registry itself. Populated at import time by tool modules.
_REGISTRY: Dict[str, Tool] = {}


def safe(func: Callable) -> Callable:
    """Wrap a tool handler so it can never crash the backend.

    Any exception is caught, logged, and turned into a failed ToolResult.
    Plain return values (str, None, dict) are normalized into ToolResult.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> ToolResult:
        try:
            result = func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - intentional catch-all
            logger.exception("Tool action '%s' raised an exception", func.__name__)
            return ToolResult(success=False, message=f"Something went wrong: {exc}")

        if isinstance(result, ToolResult):
            return result
        if result is None:
            return ToolResult(success=True, message="Done.")
        return ToolResult(success=True, message=str(result))

    return wrapper


def action(
    tool_name: str,
    action_name: str,
    description: str = "",
    required_args: Optional[List[str]] = None,
    dangerous: bool = False,
    tool_description: str = "",

    # NEW
    verify: Optional[Callable] = None,
    max_retries: int = 0,
):
    """
    Register a tool action.
    """

    def decorator(func: Callable) -> Callable:

        wrapped = safe(func)

        tool = _REGISTRY.setdefault(
            tool_name,
            Tool(name=tool_name),
        )

        if tool_description and not tool.description:
            tool.description = tool_description

        tool.add_action(
            ToolAction(
                name=action_name,
                handler=wrapped,
                description=description,
                required_args=required_args or [],
                dangerous=dangerous,

                verify=verify,
                max_retries=max_retries,
            )
        )

        return wrapped

    return decorator


def get_registry() -> Dict[str, Tool]:
    return _REGISTRY


def get_tool_names() -> List[str]:
    return list(_REGISTRY.keys())


def get_tool(tool_name: str) -> Optional[Tool]:
    return _REGISTRY.get(tool_name)


def call_handler(handler: Callable, args: Dict[str, Any]) -> ToolResult:
    """Call a handler with only the kwargs it actually accepts.

    Lets tool handlers use plain, explicit parameter names (contact, message,
    path, ...) while the executor keeps passing the whole args dict from the
    planner without needing to know each handler's exact signature.
    """

    sig = inspect.signature(handler)
    accepts_kwargs = any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    if accepts_kwargs:
        call_args = {k: v for k, v in args.items() if k != "action"}
    else:
        call_args = {
            k: v for k, v in args.items() if k in sig.parameters and k != "action"
        }
    return handler(**call_args)


def describe_tools() -> str:
    """Human/LLM-readable listing of every tool + action, for the planner prompt."""

    lines = []
    for tool in _REGISTRY.values():
        lines.append(f"- {tool.name}: {tool.description}")
        for act in tool.actions.values():
            args_hint = f" (args: {', '.join(act.required_args)})" if act.required_args else ""
            danger_hint = " [requires confirmation]" if act.dangerous else ""
            lines.append(f'    - action "{act.name}"{args_hint}{danger_hint}: {act.description}')
    return "\n".join(lines)
