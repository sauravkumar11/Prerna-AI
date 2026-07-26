"""
WhatsApp tool
=============
Thin registry wrapper around whatsapp_actions.py (the actual UI-automation
logic there is unchanged).

FIXED (found via a real production trace log): whatsapp_actions.py's
functions all return (success, message) tuples — they report honest
failure now instead of always claiming success — but every wrapper here
was still doing `ToolResult(True, _action(...))`, hardcoding success=True
and passing the WHOLE TUPLE as the message string. That crashed
executor.py's `" ".join(messages)` the moment any WhatsApp action ran
(TypeError: sequence item 0: expected str instance, tuple found) and, even
where it didn't crash, silently reported success on every real failure.
Every call site below now unpacks (success, message) and passes both
through honestly.
"""

from __future__ import annotations

from agent.registry import ToolResult, action
from whatsapp_actions import (
    open_whatsapp as _open_whatsapp,
    search_contact as _search_contact,
    send_message as _send_message,
    voice_call as _voice_call,
    video_call as _video_call,
    archive_chat as _archive_chat,
    unarchive_chat as _unarchive_chat,
    mute_contact as _mute_contact,
    delete_chat as _delete_chat,
    mark_as_read as _mark_as_read,
    mark_as_unread as _mark_as_unread,
    block_contact as _block_contact,
    unblock_contact as _unblock_contact,
    pin_chat as _pin_chat,
    unpin_chat as _unpin_chat,
)

TOOL_DESCRIPTION = (
    "Control WhatsApp Desktop: open it, open a chat, send messages, make "
    "voice/video calls, and manage a chat — archive, mute, delete, mark "
    "read/unread, pin/unpin, and block/unblock a contact."
)


@action("whatsapp", "open", "Open WhatsApp Desktop.", tool_description=TOOL_DESCRIPTION)
def open_whatsapp() -> ToolResult:
    success, message = _open_whatsapp()
    return ToolResult(success, message)


@action("whatsapp", "open_chat", "Open a specific contact's chat (without sending anything).", required_args=["contact"])
def open_chat(contact: str) -> ToolResult:
    success, open_message = _open_whatsapp()
    if not success:
        return ToolResult(False, open_message)
    found = _search_contact(contact)
    if not found:
        return ToolResult(False, f"Couldn't find or open {contact}'s chat.")
    return ToolResult(True, f"Opened chat with {contact}.")


@action(
    "whatsapp",
    "send_message",
    "Send a WhatsApp text message to a contact.",
    required_args=["contact", "message"],
)
def send_message(contact: str, message: str) -> ToolResult:
    success, result_message = _send_message(contact, message)
    return ToolResult(success, result_message)


@action(
    "whatsapp",
    "voice_call",
    "Start a WhatsApp voice call with a contact.",
    required_args=["contact"],
)
def voice_call(contact: str) -> ToolResult:
    success, message = _voice_call(contact)
    return ToolResult(success, message)


@action(
    "whatsapp",
    "video_call",
    "Start a WhatsApp video call with a contact.",
    required_args=["contact"],
)
def video_call(contact: str) -> ToolResult:
    success, message = _video_call(contact)
    return ToolResult(success, message)


@action(
    "whatsapp",
    "archive_chat",
    "Archive a contact's chat.",
    required_args=["contact"],
)
def archive_chat(contact: str) -> ToolResult:
    success, message = _archive_chat(contact)
    return ToolResult(success, message)


@action(
    "whatsapp",
    "unarchive_chat",
    "Unarchive a contact's chat.",
    required_args=["contact"],
)
def unarchive_chat(contact: str) -> ToolResult:
    success, message = _unarchive_chat(contact)
    return ToolResult(success, message)


@action(
    "whatsapp",
    "mute",
    "Mute notifications from a contact.",
    required_args=["contact"],
)
def mute(contact: str) -> ToolResult:
    success, message = _mute_contact(contact)
    return ToolResult(success, message)


@action(
    "whatsapp",
    "delete_chat",
    "Delete a contact's chat history.",
    required_args=["contact"],
    dangerous=True,
)
def delete_chat(contact: str) -> ToolResult:
    success, message = _delete_chat(contact)
    return ToolResult(success, message)


@action(
    "whatsapp",
    "mark_as_read",
    "Mark a contact's chat as read.",
    required_args=["contact"],
)
def mark_as_read(contact: str) -> ToolResult:
    success, message = _mark_as_read(contact)
    return ToolResult(success, message)


@action(
    "whatsapp",
    "mark_as_unread",
    "Mark a contact's chat as unread.",
    required_args=["contact"],
)
def mark_as_unread(contact: str) -> ToolResult:
    success, message = _mark_as_unread(contact)
    return ToolResult(success, message)


@action(
    "whatsapp",
    "block",
    "Block a contact on WhatsApp.",
    required_args=["contact"],
    dangerous=True,
)
def block(contact: str) -> ToolResult:
    success, message = _block_contact(contact)
    return ToolResult(success, message)


@action(
    "whatsapp",
    "unblock",
    "Unblock a contact on WhatsApp.",
    required_args=["contact"],
)
def unblock(contact: str) -> ToolResult:
    success, message = _unblock_contact(contact)
    return ToolResult(success, message)


@action(
    "whatsapp",
    "pin_chat",
    "Pin a contact's chat to the top of the chat list.",
    required_args=["contact"],
)
def pin_chat(contact: str) -> ToolResult:
    success, message = _pin_chat(contact)
    return ToolResult(success, message)


@action(
    "whatsapp",
    "unpin_chat",
    "Unpin a contact's chat.",
    required_args=["contact"],
)
def unpin_chat(contact: str) -> ToolResult:
    success, message = _unpin_chat(contact)
    return ToolResult(success, message)