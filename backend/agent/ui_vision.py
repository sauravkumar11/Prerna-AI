"""
UI Vision — semantic element finding
=====================================
The real version of "Click(Button=Send) instead of Click(823,442)".

Built on Windows UI Automation (UIA) — the same accessibility tree screen
readers use, which Chrome, VS Code, Explorer, Word, and Excel all already
implement. This asks the OS directly "where's the button named Send"
instead of screen-scraping for it. That's not a shortcut — it's the
correct approach: UIA is faster, doesn't break when a theme/font changes,
and works identically across every standard Windows app without any
per-app computer-vision model. Computer vision / OCR (agent.ocr) is the
FALLBACK for the minority of cases UIA can't see into (canvas-rendered
content, video players, some poorly-accessible Electron apps) — not the
primary mechanism.

Honesty note: this module degrades gracefully if the `uiautomation`
package isn't installed (find_element/find_window return None rather than
crashing), same pattern as agent.verification's process_running /
window_title_contains. But a missing dependency is the SMALL uncertainty
here — the real one is that none of the actual Windows UIA behavior (does
it find the button, is the tree shaped the way I expect, does a given
Electron app expose good accessibility info at all) can be verified in
this environment. Only the matching/traversal LOGIC is tested here, using
fake control objects — the real COM calls need a real Windows session.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterator, List, Optional, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)

try:
    import uiautomation as auto
    _HAS_UIA = True
except ImportError:
    _HAS_UIA = False
    logger.debug("ui_vision: 'uiautomation' package not installed — semantic finding disabled")


@dataclass
class ElementInfo:
    name: str
    control_type: str
    automation_id: str
    rect: Tuple[int, int, int, int]  # left, top, right, bottom
    is_enabled: bool

    @property
    def center(self) -> Tuple[int, int]:
        left, top, right, bottom = self.rect
        return ((left + right) // 2, (top + bottom) // 2)


# ── Traversal (pure logic — tested with fakes, no OS dependency) ──────────

def walk(control, max_depth: int = 6) -> Iterator[object]:
    """Depth-limited traversal. A real UIA tree (especially a browser tab)
    can have thousands of nodes — capping depth means a pathological page
    can't make a search hang, at the cost of not seeing very deeply nested
    controls. 6 covers ordinary app chrome/dialogs/toolbars; deep custom
    web app UIs may need a caller-specified higher depth."""
    stack = [(control, 0)]
    while stack:
        node, depth = stack.pop()
        yield node
        if depth >= max_depth:
            continue
        try:
            children = node.GetChildren()
        except Exception:
            continue
        for child in children:
            stack.append((child, depth + 1))


def _matches(control, name: Optional[str], control_type: Optional[str]) -> bool:
    try:
        if control_type and getattr(control, "ControlTypeName", None) != control_type:
            return False
        if name:
            control_name = (getattr(control, "Name", None) or "").lower()
            if name.lower() not in control_name:
                return False
        rect = getattr(control, "BoundingRectangle", None)
        if not rect:
            return False  # invisible/unrendered controls aren't clickable targets
        return True
    except Exception:
        return False


def _to_element_info(control) -> ElementInfo:
    rect = control.BoundingRectangle
    return ElementInfo(
        name=control.Name or "",
        control_type=getattr(control, "ControlTypeName", "") or "",
        automation_id=getattr(control, "AutomationId", "") or "",
        rect=(rect.left, rect.top, rect.right, rect.bottom),
        is_enabled=bool(getattr(control, "IsEnabled", True)),
    )


def search(root, name: Optional[str] = None, control_type: Optional[str] = None,
           max_depth: int = 6) -> Optional[object]:
    """First matching control under `root`, or None. Separated from
    find_element() so the matching logic can be unit tested against fake
    control trees without touching the real UIA API."""
    for control in walk(root, max_depth=max_depth):
        if _matches(control, name, control_type):
            return control
    return None


# ── Real OS entry points (need a live Windows session, untestable here) ───

def find_window(title_substring: str, timeout: float = 3.0):
    """Top-level window whose title contains title_substring
    (case-insensitive). Returns the UIA control, or None if not found
    within `timeout` — polls rather than failing instantly, since a
    just-launched app's window may not exist yet."""
    if not _HAS_UIA:
        return None
    needle = title_substring.lower()
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            for w in auto.GetRootControl().GetChildren():
                if needle in (w.Name or "").lower():
                    return w
        except Exception as exc:
            logger.debug("find_window: enumeration failed: %s", exc)
        time.sleep(0.2)
    return None


def find_element(
    window_title_substring: str,
    name: Optional[str] = None,
    control_type: Optional[str] = None,
    timeout: float = 3.0,
) -> Optional[ElementInfo]:
    """The Click(Button=Send) primitive. Finds a control by visible name
    (case-insensitive substring) and/or control type, inside a window
    matched by title. Returns None on no match — NEVER guesses a fallback
    coordinate. The caller decides what a miss means (retry, re-plan,
    fall back to OCR, tell the user it couldn't find it)."""
    if not _HAS_UIA:
        logger.debug("find_element: uiautomation not installed")
        return None

    window = find_window(window_title_substring, timeout=timeout)
    if window is None:
        return None

    deadline = time.time() + timeout
    while time.time() < deadline:
        control = search(window, name=name, control_type=control_type)
        if control is not None:
            try:
                return _to_element_info(control)
            except Exception as exc:
                logger.debug("find_element: control found but info extraction failed: %s", exc)
        time.sleep(0.2)
    return None


def click_element(element: ElementInfo) -> bool:
    """Click at the element's center. This is the only place a coordinate
    is used — but it's DERIVED fresh from the semantic match, not
    hardcoded or cached. If the window moves or the layout changes,
    calling find_element() again gets a correct coordinate; nothing here
    assumes yesterday's position is still valid."""
    try:
        import pyautogui
        pyautogui.click(*element.center)
        return True
    except Exception as exc:
        logger.debug("click_element failed: %s", exc)
        return False


def click_by_name(
    window_title_substring: str,
    name: str,
    control_type: Optional[str] = None,
    timeout: float = 3.0,
) -> bool:
    """Convenience: find + click in one call. Returns False (not an
    exception) on a miss, so callers can treat it like any other tool
    action that didn't work rather than crashing the request."""
    element = find_element(window_title_substring, name=name, control_type=control_type, timeout=timeout)
    if element is None:
        return False
    return click_element(element)


# ── Verify-function integration (agent.verification) ──────────────────────
# Lets a tool action declare verify=element_visible(...) exactly like the
# existing process_running(...)/window_title_contains(...) verifiers — the
# same honest True/False/None contract: False only when we're CONFIDENT
# the element genuinely isn't there, None if we can't tell (no uiautomation
# installed), never a guess.

def element_visible(window_title_substring: str, name: str, control_type: Optional[str] = None):
    def _verify(args, result):
        if not _HAS_UIA:
            return None
        element = find_element(window_title_substring, name=name, control_type=control_type, timeout=1.5)
        return element is not None
    return _verify