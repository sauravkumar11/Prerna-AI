"""
Instagram tool
===============
Navigation (open app, open a profile, open reels, open messages) works
reliably via direct URLs.

Intentionally NOT included: auto-scrolling reels or auto-liking posts.
That requires simulating a logged-in user repeatedly interacting with
content, which is exactly the kind of automated engagement Instagram's
terms of service prohibit and can get an account flagged/limited. Opening
reels/messages for you to interact with is fine; doing the interacting for
you isn't something I'd want to quietly wire up.
"""

from __future__ import annotations

import webbrowser

from agent.registry import ToolResult, action

TOOL_DESCRIPTION = "Open Instagram, a profile, reels, or your messages."


@action("instagram", "open", "Open Instagram's homepage.", tool_description=TOOL_DESCRIPTION)
def open_instagram() -> ToolResult:
    webbrowser.open("https://instagram.com")
    return ToolResult(True, "Opening Instagram.")


@action("instagram", "open_profile", "Open a specific user's profile.", required_args=["username"])
def open_profile(username: str) -> ToolResult:
    handle = username.strip().lstrip("@")
    webbrowser.open(f"https://instagram.com/{handle}/")
    return ToolResult(True, f"Opening @{handle}'s profile.")


@action("instagram", "open_reels", "Open the Reels tab.")
def open_reels() -> ToolResult:
    webbrowser.open("https://instagram.com/reels/")
    return ToolResult(True, "Opening Reels.")


@action("instagram", "open_messages", "Open Instagram Direct messages.")
def open_messages() -> ToolResult:
    webbrowser.open("https://instagram.com/direct/inbox/")
    return ToolResult(True, "Opening your messages.")
