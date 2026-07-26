"""
Email tool
==========
`compose` uses a `mailto:` link, so it opens whatever the user's default
mail handler is (desktop Outlook, or Gmail in the browser if that's the
default) - more reliable than assuming one specific provider.
"""

from __future__ import annotations

import webbrowser
from urllib.parse import quote

from agent.registry import ToolResult, action

TOOL_DESCRIPTION = "Compose an email, or search your inbox on Gmail/Outlook."


@action("email", "compose", "Compose a new email (opens your default mail app).", tool_description=TOOL_DESCRIPTION)
def compose(to: str = "", subject: str = "", body: str = "") -> ToolResult:
    url = f"mailto:{quote(to)}?subject={quote(subject)}&body={quote(body)}"
    webbrowser.open(url)
    return ToolResult(True, "Opening a new email draft.")


@action("email", "search_gmail", "Search Gmail.", required_args=["query"])
def search_gmail(query: str) -> ToolResult:
    webbrowser.open(f"https://mail.google.com/mail/u/0/#search/{quote(query)}")
    return ToolResult(True, f'Searching Gmail for "{query}".')
