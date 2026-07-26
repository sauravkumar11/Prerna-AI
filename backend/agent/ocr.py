"""
OCR fallback
============
For the minority of screen content Windows UI Automation genuinely can't
see into: canvas-rendered graphics, video players, images, and some
poorly-accessible Electron apps. NOT the primary way Prerna understands
UI — agent.ui_vision (real accessibility tree) is faster and more
reliable for anything that exposes one, which is most standard apps.
Reach for this only when ui_vision comes up empty.

Requires pytesseract (pip) AND the actual Tesseract OCR binary installed
separately on Windows (https://github.com/UB-Mannheim/tesseract/wiki) —
pip alone does not install the engine, just the Python wrapper around it.
This module checks for both and degrades honestly (returns None with a
clear log message) rather than crashing if either is missing, same
pattern as every other optional-dependency check in this codebase.
"""

from __future__ import annotations

from typing import Optional, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)

try:
    import pytesseract
    from PIL import Image
    _HAS_PYTESSERACT = True
except ImportError:
    _HAS_PYTESSERACT = False
    logger.debug("ocr: pytesseract/Pillow not installed — OCR fallback disabled")


def _tesseract_binary_available() -> bool:
    if not _HAS_PYTESSERACT:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        logger.debug(
            "ocr: pytesseract installed but the Tesseract binary itself wasn't found — "
            "install it separately (not just `pip install pytesseract`): "
            "https://github.com/UB-Mannheim/tesseract/wiki"
        )
        return False


def read_screen(region: Optional[Tuple[int, int, int, int]] = None) -> Optional[str]:
    """OCR the full screen, or a region (left, top, right, bottom) if given
    — e.g. a specific dialog/tooltip's bounding rect from ui_vision, when
    you know roughly where something is but UIA can't read its text
    directly (a canvas-drawn label, for instance).

    Returns None (not an exception, not empty-string-as-silent-failure) if
    OCR genuinely isn't available here — callers should treat None as
    "couldn't check" and fall back to asking the user, not as "no text
    found."
    """
    if not _tesseract_binary_available():
        return None

    try:
        import pyautogui
        screenshot = pyautogui.screenshot(region=_to_pyautogui_region(region) if region else None)
        text = pytesseract.image_to_string(screenshot)
        return text.strip()
    except Exception as exc:
        logger.debug("ocr.read_screen failed: %s", exc)
        return None


def _to_pyautogui_region(rect: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
    """pyautogui.screenshot(region=...) wants (left, top, width, height);
    ui_vision.ElementInfo.rect is (left, top, right, bottom) — convert."""
    left, top, right, bottom = rect
    return (left, top, right - left, bottom - top)