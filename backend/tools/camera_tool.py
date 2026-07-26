"""
Camera tool
===========
`open`    — launches the Windows Camera app
`capture` — takes a photo via OpenCV directly (no UI needed, fastest)
`take_picture` — opens the Windows Camera app, waits for it to be ready,
                 then clicks the capture button via pyautogui. Use this when
                 the user says "open camera and click picture" and expects to
                 see the Camera app UI used rather than a silent webcam grab.
"""

from __future__ import annotations

import subprocess
import time
from datetime import datetime
from pathlib import Path

import cv2
import pyautogui

from agent.registry import ToolResult, action
from agent.verification import window_title_contains, window_title_absent
from config.settings import CAMERA_CAPTURE_DIR
from utils.logger import get_logger

logger = get_logger(__name__)

TOOL_DESCRIPTION = "Open the Camera app, auto-click the shutter, or capture a photo directly."

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3

# Windows Camera's default save location. The user can change this in the
# Camera app's own settings, but this covers the default/common case.
_CAMERA_ROLL_DIR = Path.home() / "Pictures" / "Camera Roll"
_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def _find_newest_photo(directory: Path, since: float, timeout: float = 6.0) -> Path | None:
    """Poll `directory` for an image file modified at/after `since`
    (a time.time() timestamp taken right before the shutter click), for up
    to `timeout` seconds. Windows Camera writes the file asynchronously
    after the shutter sound, so a short poll (not a single check) is needed.
    Returns the newest matching Path, or None if nothing new appears in time.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            candidates = [
                p for p in directory.glob("*")
                if p.suffix.lower() in _PHOTO_EXTENSIONS and p.stat().st_mtime >= since
            ]
            if candidates:
                return max(candidates, key=lambda p: p.stat().st_mtime)
        except FileNotFoundError:
            pass  # Camera Roll folder doesn't exist yet — keep polling briefly
        time.sleep(0.5)
    return None


def _wait_for_camera_window(timeout: float = 8.0) -> bool:
    """Return True once the Camera window is in the foreground, or False on timeout."""
    try:
        import win32gui
    except ImportError:
        time.sleep(3)  # best-effort wait if pywin32 isn't available
        return True

    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd).lower()
        if "camera" in title:
            return True
        time.sleep(0.4)
    return False


def _get_camera_window_rect():
    """Return (left, top, right, bottom) of the foreground Camera window,
    or None if pywin32 isn't available or the foreground window isn't Camera."""
    try:
        import win32gui
    except ImportError:
        return None

    hwnd = win32gui.GetForegroundWindow()
    if "camera" not in win32gui.GetWindowText(hwnd).lower():
        return None
    return win32gui.GetWindowRect(hwnd)


def _click_camera_shutter() -> bool:
    """
    Click the Camera app's capture button.

    Previously this assumed the Camera window filled the entire screen and
    clicked a fixed screen-relative coordinate — which misses entirely if
    the window isn't maximized, is on a different-sized display, or isn't
    positioned at the screen origin. Now clicks relative to the ACTUAL
    Camera window's bounds, and also sends Enter as a second trigger
    (Windows Camera also captures on Enter/Space when it has focus), so a
    slightly-off click position still results in a photo being taken.
    """
    # Give the camera a moment to fully render
    time.sleep(1.5)

    rect = _get_camera_window_rect()
    if rect:
        left, top, right, bottom = rect
        click_x = (left + right) // 2
        click_y = top + int((bottom - top) * 0.90)
    else:
        # No window handle available — fall back to the old screen-relative
        # guess (better than nothing, e.g. if pywin32 is missing).
        screen_w, screen_h = pyautogui.size()
        click_x = screen_w // 2
        click_y = int(screen_h * 0.90)

    pyautogui.click(click_x, click_y)
    time.sleep(0.5)
    # Redundant trigger in case the click missed the actual button —
    # harmless no-op if the click already worked.
    pyautogui.press("enter")
    time.sleep(0.5)
    return True


@action(
    "camera", "open", "Open the Windows Camera app.", tool_description=TOOL_DESCRIPTION,
    verify=window_title_contains("camera"), max_retries=1,
)
def open_camera() -> ToolResult:
    subprocess.Popen("start microsoft.windows.camera:", shell=True)
    return ToolResult(True, "Opening Camera.")


@action(
    "camera", "close", "Close the Windows Camera app.",
    verify=window_title_absent("camera"), max_retries=1,
)
def close_camera() -> ToolResult:
    """Close the Camera app window. Tries a graceful WM_CLOSE to the window
    first, then falls back to killing the process by name if that fails
    (e.g. win32gui unavailable, or window already minimized to tray)."""
    closed = False

    try:
        import win32con
        import win32gui

        def _enum_handler(hwnd, _):
            nonlocal closed
            if win32gui.IsWindowVisible(hwnd) and "camera" in win32gui.GetWindowText(hwnd).lower():
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                closed = True

        win32gui.EnumWindows(_enum_handler, None)
    except ImportError:
        logger.warning("pywin32 not available — falling back to taskkill for camera.close")
    except Exception as exc:
        logger.warning("EnumWindows failed while closing Camera: %s", exc)

    if not closed:
        try:
            result = subprocess.run(
                ["taskkill", "/IM", "WindowsCamera.exe", "/F"],
                capture_output=True,
                timeout=5,
                text=True,
            )
            closed = result.returncode == 0
        except Exception as exc:
            logger.warning("taskkill fallback failed: %s", exc)

    if closed:
        return ToolResult(True, "Camera closed.", speech="Camera closed.")
    return ToolResult(False, "I couldn't find the Camera app window to close — it might already be closed.")


def _verify_take_picture(args: Dict[str, Any], result: Any) -> Optional[bool]:
    """True only when a confirmed real path was found (see take_picture's
    _find_newest_photo call) — False otherwise. Unlike the window-presence
    verifiers, this isn't a "can't check from here" case: the check DID
    run and found no new file, which is a real (if not 100% certain, since
    the user could have a non-default save folder) negative signal — worth
    treating as a genuine retry trigger rather than staying silent."""
    data = getattr(result, "data", None) or {}
    return bool(data.get("path"))


@action(
    "camera", "take_picture",
    "Open the Windows Camera app and automatically click the shutter button to take a photo.",
    verify=_verify_take_picture, max_retries=1,
)
def take_picture() -> ToolResult:
    """Open Camera app → wait until ready → click shutter → confirm."""
    subprocess.Popen("start microsoft.windows.camera:", shell=True)

    ready = _wait_for_camera_window(timeout=10)
    if not ready:
        return ToolResult(
            False,
            "The Camera app didn't open in time. Try saying 'take picture' again once it's open.",
        )

    capture_time = time.time()
    _click_camera_shutter()

    # Windows Camera decides the filename itself — without this, there was
    # no real path anywhere, so a later "open the picture" had nothing
    # legitimate to open (it was falling back to guessing folder names).
    photo = _find_newest_photo(_CAMERA_ROLL_DIR, since=capture_time)
    if photo:
        return ToolResult(
            True,
            f"Photo taken! Saved as {photo.name} in Camera Roll.",
            data={"path": str(photo)},
            speech="Photo taken!",
        )

    return ToolResult(
        True,
        "Photo taken! It should be in your Pictures > Camera Roll folder, "
        "though I couldn't confirm the exact filename just now.",
        data={"saved_to": str(_CAMERA_ROLL_DIR)},
        speech="Photo taken!",
    )


@action("camera", "capture",
        "Silently capture a photo via the webcam (no Camera app UI needed) and save it.")
def capture(device_index: int = 0) -> ToolResult:
    cap = cv2.VideoCapture(device_index)
    try:
        if not cap.isOpened():
            return ToolResult(
                False,
                "I couldn't access the webcam - it might be in use by another app.",
            )

        # Warm up: discard a few frames so auto-exposure settles
        for _ in range(5):
            cap.read()
        ok, frame = cap.read()
        if not ok:
            return ToolResult(False, "Couldn't capture a frame from the webcam.")

        CAMERA_CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        filename = datetime.now().strftime("capture_%Y%m%d_%H%M%S.jpg")
        path = CAMERA_CAPTURE_DIR / filename
        cv2.imwrite(str(path), frame)

        return ToolResult(
            True,
            f"Photo saved as {filename}.",
            data={"path": str(path)},
            speech="Photo saved.",
        )
    finally:
        cap.release()
