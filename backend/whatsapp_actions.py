"""
WhatsApp Desktop Automation
============================
All actions verify the WhatsApp window is focused before interacting,
so a popup or notification can't cause pyautogui to type into the wrong app.

THREE interaction styles are used, in order of preference:

1. KEYBOARD SHORTCUTS — used wherever WhatsApp Desktop actually ships an
   official shortcut (archive, mute, delete, mark unread). These are the
   most reliable actions in this file: no image matching, no screen
   resolution dependence.

2. UI AUTOMATION (accessibility tree, via pywinauto) — used for menu items
   with no shortcut (block/unblock, pin/unpin). Finds the menu item by its
   ACTUAL NAME in Windows' accessibility tree rather than matching pixels —
   works regardless of theme, DPI scaling, or WhatsApp version, and covers
   any future menu item by name with no per-feature screenshot needed.
   Caveat, stated plainly: WhatsApp Desktop is Electron/Chromium, and
   Chromium apps sometimes only fully populate their accessibility tree
   once assistive technology is detected as running — see
   _nudge_accessibility_engine(). This has NOT been verified against a
   live WhatsApp Desktop install; it's the right architecture, but whether
   it actually finds these controls needs to be tested for real.

3. CONTEXT-MENU + TEMPLATE MATCHING (pixel image matching) — the ORIGINAL
   fallback, kept as tier 3: if UI Automation doesn't find the item (e.g.
   pywinauto unavailable, or WhatsApp's accessibility tree isn't exposed),
   fall back to matching a small cropped screenshot saved under assets/
   (see MENU_ICON_HINTS). If that's also missing, the action degrades
   gracefully and tells the user to finish it manually
   instead of clicking blindly into the wrong place.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import time

import pyautogui
import pyperclip

from utils.logger import get_logger

logger = get_logger(__name__)

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.4

BASE_DIR = os.path.dirname(__file__)
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

VOICE_ICON = os.path.join(ASSETS_DIR, "voice_call.png")
VIDEO_ICON = os.path.join(ASSETS_DIR, "video_call.png")

# Optional template screenshots for context-menu items that have no
# keyboard shortcut. Drop matching crops into backend/assets/ (same way
# voice_call.png / video_call.png were captured) to enable these actions;
# until then, the action falls back to opening the menu and asking the
# user to finish the click themselves rather than guessing coordinates.
MENU_ICON_HINTS = {
    "block":   os.path.join(ASSETS_DIR, "block_menu_item.png"),
    "unblock": os.path.join(ASSETS_DIR, "unblock_menu_item.png"),
    "pin":     os.path.join(ASSETS_DIR, "pin_menu_item.png"),
    "unpin":   os.path.join(ASSETS_DIR, "unpin_menu_item.png"),
    "block_confirm": os.path.join(ASSETS_DIR, "block_confirm_button.png"),
}

# Accessible names to try via UI Automation (tier 1, see module docstring)
# before falling back to pixel template matching (tier 3). Multiple
# candidates per key since WhatsApp's exact menu label isn't confirmed
# without live testing — e.g. it may say "Block" or "Block contact".
MENU_ITEM_NAMES = {
    "block": ["Block", "Block contact"],
    "unblock": ["Unblock", "Unblock contact"],
    "pin": ["Pin chat", "Pin"],
    "unpin": ["Unpin chat", "Unpin"],
    "block_confirm": ["Block"],
}


def _ensure_whatsapp_focused(timeout: float = 8.0) -> bool:
    """Return True only once WhatsApp Desktop is the foreground window."""
    try:
        import win32gui
    except ImportError:
        logger.warning("pywin32 not available — skipping window focus check")
        time.sleep(2)
        return True

    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd).lower()
        if "whatsapp" in title:
            return True
        time.sleep(0.4)

    logger.warning("WhatsApp window did not come to foreground within %.1fs", timeout)
    return False


def _type_text(text: str) -> None:
    """Paste via clipboard (faster and handles Unicode better than typewrite)."""
    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v")


_accessibility_nudged = False


def _nudge_accessibility_engine() -> None:
    """Chromium/Electron apps (WhatsApp Desktop included) sometimes only
    fully populate their UI Automation tree once assistive technology is
    detected as running. Signaling SPI_SETSCREENREADER is a known trick to
    trigger that in some Chromium builds — best-effort, silently does
    nothing if unavailable. Only run once per process; harmless to call
    repeatedly but pointless.

    NOTE: this is a documented technique for Chromium accessibility in
    general, but has NOT been confirmed against WhatsApp Desktop
    specifically — it may simply not be necessary, or may not be
    sufficient, for this particular Electron build. Treat the whole UIA
    tier as unverified until tested live.
    """
    global _accessibility_nudged
    if _accessibility_nudged:
        return
    _accessibility_nudged = True
    try:
        SPI_SETSCREENREADER = 0x0047
        ctypes.windll.user32.SystemParametersInfoW(SPI_SETSCREENREADER, 1, None, 0)
    except Exception as exc:
        logger.debug("Accessibility-engine nudge failed (non-fatal): %s", exc)


def _click_menu_item_by_name(hint_key: str, timeout: float = 2.0) -> bool:
    """Tier 1: find a context-menu item by its ACTUAL accessible name via
    Windows UI Automation, instead of matching pixels. Works across any
    theme/DPI/WhatsApp version if the accessibility tree exposes it — see
    the caveat in this module's docstring about whether it actually does.
    Returns False (never raises) so callers can fall through to tier 3.
    """
    names = MENU_ITEM_NAMES.get(hint_key)
    if not names:
        return False

    try:
        from pywinauto import Desktop
    except ImportError:
        logger.debug("pywinauto not installed — skipping UIA tier for '%s'", hint_key)
        return False

    _nudge_accessibility_engine()

    try:
        whatsapp_window = Desktop(backend="uia").window(title_re=".*WhatsApp.*")
        for name in names:
            try:
                item = whatsapp_window.child_window(title=name, control_type="MenuItem")
                if item.exists(timeout=timeout):
                    item.click_input()
                    logger.info("Clicked '%s' via UI Automation (accessible name match).", name)
                    return True
            except Exception:
                continue
    except Exception as exc:
        logger.debug("UI Automation lookup failed for '%s': %s", hint_key, exc)

    return False


def _click_menu_item(hint_key: str, confidence: float = 0.8, timeout: float = 2.0) -> bool:
    """Click a context-menu item — tries UI Automation by accessible name
    first (tier 1, generalizes to any menu item with zero screenshots),
    then falls back to its saved template image (tier 3) if that doesn't
    find anything. Returns False (without raising) only if BOTH tiers
    come up empty, so callers can fall back to a friendly manual-finish
    message."""
    if _click_menu_item_by_name(hint_key, timeout=timeout):
        return True

    path = MENU_ICON_HINTS.get(hint_key)
    if not path or not os.path.exists(path):
        return False

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            location = pyautogui.locateOnScreen(path, confidence=confidence)
            if location:
                pyautogui.click(pyautogui.center(location))
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def open_whatsapp() -> tuple[bool, str]:
    subprocess.Popen("start whatsapp:", shell=True)
    if not _ensure_whatsapp_focused(timeout=10):
        return False, "Opened WhatsApp, but it took too long to appear. Please check if WhatsApp Desktop is installed."
    return True, "WhatsApp is open."


def search_contact(name: str) -> bool:
    """Returns True only if the search actually completed with WhatsApp
    focused throughout — False (not None/silent) so callers can honestly
    report a failure instead of assuming it worked."""
    if not _ensure_whatsapp_focused():
        logger.error("Cannot search contact — WhatsApp is not focused.")
        return False

    pyautogui.hotkey("ctrl", "f")
    time.sleep(0.8)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.press("backspace")
    _type_text(name)
    time.sleep(1.5)
    pyautogui.press("enter")
    time.sleep(1.5)
    return True


def _open_chat_context_menu(contact: str) -> bool:
    """Search for a contact, then right-click the (now highlighted) chat
    list entry to open its context menu — this is where WhatsApp Desktop
    puts block/unblock/pin/mute/archive/delete for a chat."""
    opened, _ = open_whatsapp()
    if not opened or not search_contact(contact):
        return False
    if not _ensure_whatsapp_focused():
        return False

    # The active/highlighted search result sits at the top of the chat
    # list; Down+Up keeps focus there without changing selection, then a
    # right-click on the currently focused row opens its context menu.
    pyautogui.press("down")
    pyautogui.press("up")
    pyautogui.hotkey("shift", "f10")  # context-menu key equivalent of right-click
    time.sleep(0.6)
    return True


def send_message(contact: str, message: str) -> tuple[bool, str]:
    open_whatsapp()
    if not search_contact(contact):
        return False, f"WhatsApp lost focus while trying to message {contact}. Please try again."

    if not _ensure_whatsapp_focused():
        return False, f"WhatsApp lost focus while trying to message {contact}. Please try again."

    _type_text(message)
    time.sleep(0.5)
    pyautogui.press("enter")
    logger.info("Message sent to %s", contact)
    return True, f"Message sent to {contact}."


def voice_call(contact: str) -> tuple[bool, str]:
    open_whatsapp()
    if not search_contact(contact):
        return False, "WhatsApp lost focus. Please try the call again."

    if not _ensure_whatsapp_focused():
        return False, "WhatsApp lost focus. Please try the call again."

    time.sleep(1)
    try:
        location = pyautogui.locateOnScreen(VOICE_ICON, confidence=0.8)
        if location:
            pyautogui.click(location)
            return True, f"Voice call started with {contact}."
    except Exception:
        pass

    logger.warning("Could not find voice call icon for %s", contact)
    return False, f"Opened {contact}'s chat, but couldn't find the call button. Please tap it manually."


def video_call(contact: str) -> tuple[bool, str]:
    open_whatsapp()
    if not search_contact(contact):
        return False, "WhatsApp lost focus. Please try the video call again."

    if not _ensure_whatsapp_focused():
        return False, "WhatsApp lost focus. Please try the video call again."

    time.sleep(1)
    try:
        location = pyautogui.locateOnScreen(VIDEO_ICON, confidence=0.8)
        if location:
            pyautogui.click(location)
            return True, f"Video call started with {contact}."
    except Exception:
        pass

    logger.warning("Could not find video call icon for %s", contact)
    return False, f"Opened {contact}'s chat, but couldn't find the video call button. Please tap it manually."


# ── Keyboard-shortcut actions (reliable — no image matching needed) ────────

def archive_chat(contact: str) -> tuple[bool, str]:
    open_whatsapp()
    if not search_contact(contact):
        return False, f"WhatsApp lost focus while archiving {contact}'s chat."
    if not _ensure_whatsapp_focused():
        return False, f"WhatsApp lost focus while archiving {contact}'s chat."
    pyautogui.hotkey("ctrl", "e")
    logger.info("Archived chat with %s", contact)
    return True, f"Archived the chat with {contact}."


def unarchive_chat(contact: str) -> tuple[bool, str]:
    # WhatsApp Desktop toggles archive state with the same shortcut.
    success, message = archive_chat(contact)
    return success, message.replace("Archived", "Unarchived")


def mute_contact(contact: str) -> tuple[bool, str]:
    open_whatsapp()
    if not search_contact(contact):
        return False, f"WhatsApp lost focus while muting {contact}."
    if not _ensure_whatsapp_focused():
        return False, f"WhatsApp lost focus while muting {contact}."
    pyautogui.hotkey("ctrl", "shift", "m")
    time.sleep(0.5)
    # The mute shortcut opens a duration submenu (8 hours / 1 week /
    # Always) — default to "Always" (last option) via keyboard nav.
    pyautogui.press("down", presses=3, interval=0.15)
    pyautogui.press("enter")
    logger.info("Muted chat with %s", contact)
    return True, f"Muted notifications from {contact}."


def delete_chat(contact: str) -> tuple[bool, str]:
    open_whatsapp()
    if not search_contact(contact):
        return False, f"WhatsApp lost focus while deleting {contact}'s chat."
    if not _ensure_whatsapp_focused():
        return False, f"WhatsApp lost focus while deleting {contact}'s chat."
    pyautogui.hotkey("ctrl", "backspace")
    time.sleep(0.6)
    pyautogui.press("enter")  # confirm the "Delete chat" dialog
    logger.info("Deleted chat with %s", contact)
    return True, f"Deleted the chat with {contact}."


def mark_as_unread(contact: str) -> tuple[bool, str]:
    open_whatsapp()
    if not search_contact(contact):
        return False, f"WhatsApp lost focus while updating {contact}'s chat."
    if not _ensure_whatsapp_focused():
        return False, f"WhatsApp lost focus while updating {contact}'s chat."
    pyautogui.hotkey("ctrl", "shift", "u")
    logger.info("Marked chat with %s as unread", contact)
    return True, f"Marked the chat with {contact} as unread."


def mark_as_read(contact: str) -> tuple[bool, str]:
    # Opening the chat is itself how WhatsApp marks it read — search_contact
    # already lands inside the conversation.
    open_whatsapp()
    if not search_contact(contact):
        return False, f"WhatsApp lost focus while opening {contact}'s chat."
    logger.info("Marked chat with %s as read", contact)
    return True, f"Marked the chat with {contact} as read."


# ── Context-menu actions (block/unblock/pin/unpin — no shortcut exists) ────

def _uia_available() -> bool:
    try:
        import pywinauto  # noqa: F401
        return True
    except ImportError:
        return False


def _no_way_to_find(hint_key: str) -> bool:
    """True only if BOTH detection tiers are unavailable for this item:
    pywinauto isn't installed (so the UI Automation tier can't even
    attempt a name lookup) AND no template image has been saved either.
    Used to fail fast (skip several seconds of real UI automation for a
    guaranteed-identical result) only in this genuinely hopeless case —
    otherwise, let the normal flow try UI Automation first, which needs
    no saved image at all and may well succeed on its own.
    """
    return not _uia_available() and not os.path.exists(MENU_ICON_HINTS[hint_key])


def _missing_template_message(action_label: str, hint_key: str) -> str:
    return (
        f"I can't {action_label} yet — pywinauto isn't installed (needed to find "
        f"the '{hint_key}' menu item by name) AND there's no saved template image "
        f"for it either under assets/. This isn't a transient failure, so retrying "
        f"won't help: either install pywinauto, or capture that screenshot crop."
    )


def block_contact(contact: str) -> tuple[bool, str]:
    # Fail fast: this is a permanent "asset not captured yet" state, not a
    # transient UI hiccup — checking before doing any slow real automation
    # (which goal_loop may retry up to 3x) avoids ~10-15s of guaranteed-to-fail
    # clicking/escaping for a result we already know in advance.
    if _no_way_to_find("block"):
        return False, _missing_template_message("block a contact", "block")

    if not _open_open_or_context_menu_ready(contact):
        return False, f"WhatsApp lost focus while trying to block {contact}."

    if _click_menu_item("block"):
        time.sleep(0.6)
        # Blocking asks for confirmation; click it if we have a template,
        # otherwise fall back to Enter (WhatsApp focuses the confirm
        # button by default in this dialog).
        if not _click_menu_item("block_confirm"):
            pyautogui.press("enter")
        logger.info("Blocked contact %s", contact)
        return True, f"Blocked {contact}."

    logger.warning("Could not find 'Block' menu item for %s", contact)
    pyautogui.press("escape")
    return False, (
        f"Opened {contact}'s menu, but couldn't find the 'Block' option "
        "(tried accessibility lookup and a saved image, neither found it) — please tap it manually this once."
    )


def unblock_contact(contact: str) -> tuple[bool, str]:
    if _no_way_to_find("unblock"):
        return False, _missing_template_message("unblock a contact", "unblock")

    if not _open_open_or_context_menu_ready(contact):
        return False, f"WhatsApp lost focus while trying to unblock {contact}."

    if _click_menu_item("unblock"):
        logger.info("Unblocked contact %s", contact)
        return True, f"Unblocked {contact}."

    logger.warning("Could not find 'Unblock' menu item for %s", contact)
    pyautogui.press("escape")
    return False, (
        f"Opened {contact}'s menu, but couldn't find the 'Unblock' option "
        "(tried accessibility lookup and a saved image, neither found it) — please tap it manually this once."
    )


def pin_chat(contact: str) -> tuple[bool, str]:
    if _no_way_to_find("pin"):
        return False, _missing_template_message("pin a chat", "pin")

    if not _open_open_or_context_menu_ready(contact):
        return False, f"WhatsApp lost focus while trying to pin {contact}'s chat."

    if _click_menu_item("pin"):
        logger.info("Pinned chat with %s", contact)
        return True, f"Pinned the chat with {contact}."

    logger.warning("Could not find 'Pin' menu item for %s", contact)
    pyautogui.press("escape")
    return False, (
        f"Opened {contact}'s menu, but couldn't find the 'Pin' option "
        "(tried accessibility lookup and a saved image, neither found it) — please tap it manually this once."
    )


def unpin_chat(contact: str) -> tuple[bool, str]:
    if _no_way_to_find("unpin"):
        return False, _missing_template_message("unpin a chat", "unpin")

    if not _open_open_or_context_menu_ready(contact):
        return False, f"WhatsApp lost focus while trying to unpin {contact}'s chat."

    if _click_menu_item("unpin"):
        logger.info("Unpinned chat with %s", contact)
        return True, f"Unpinned the chat with {contact}."

    logger.warning("Could not find 'Unpin' menu item for %s", contact)
    pyautogui.press("escape")
    return False, (
        f"Opened {contact}'s menu, but couldn't find the 'Unpin' option "
        "(tried accessibility lookup and a saved image, neither found it) — please tap it manually this once."
    )


def _open_open_or_context_menu_ready(contact: str) -> bool:
    """Thin wrapper kept name-distinct from `_open_chat_context_menu` for
    clarity at call sites; just opens the chat-list context menu and
    confirms WhatsApp still has focus."""
    if not _open_chat_context_menu(contact):
        return False
    return _ensure_whatsapp_focused()
