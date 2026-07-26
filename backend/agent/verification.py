"""
Verification
============
Optional, per-action verification for the executor's retry loop.

A tool's `@action(...)` can pass `verify=<callable>` — a function that takes
(args, result) and returns True / False / None:
  - True  -> confirmed the action actually worked
  - False -> confirmed it did NOT work (safe to retry / report failure)
  - None  -> couldn't tell either way (e.g. running outside Windows, or the
             signal this checks for just isn't available right now)

Only a definite False downgrades a ToolResult's success. None and True both
leave the original result alone. This distinction matters: a verifier that
can't observe anything should say "I don't know", not "it failed" — claiming
failure for something that actually worked would erode trust in Prerna's
confirmations faster than just staying silent when unsure. Same honesty
principle the rest of this codebase already follows (e.g. night light /
airplane mode opening the real settings page instead of faking success).

Ready-made verifiers, since most tools just need one of these two checks:
  - process_running(*names)      -- is any of these process names running?
  - window_title_contains(*kw)   -- is any visible window's title one of these?

Both degrade to None (not False) if the check can't run at all here (no
psutil / not on Windows) rather than reporting a false failure.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)

# (args, result) -> True / False / None
VerifyFn = Callable[[Dict[str, Any], Any], Optional[bool]]


def process_running(*names: str) -> VerifyFn:
    """Verifier: True if any of `names` (case-insensitive substrings) is a
    running process right now. None if psutil isn't available."""

    def _verify(args: Dict[str, Any], result: Any) -> Optional[bool]:
        try:
            import psutil
        except ImportError:
            logger.debug("process_running verifier: psutil unavailable, skipping check")
            return None

        wanted = [n.lower() for n in names]
        try:
            for proc in psutil.process_iter(["name"]):
                pname = (proc.info.get("name") or "").lower()
                if any(w in pname for w in wanted):
                    return True
        except Exception as exc:
            logger.debug("process_running verifier failed: %s", exc)
            return None
        return False

    return _verify


def window_title_contains(*keywords: str) -> VerifyFn:
    """Verifier: True if any visible top-level window's title contains one
    of `keywords` (case-insensitive). None outside Windows / without pywin32,
    since this check can only ever run there."""

    def _verify(args: Dict[str, Any], result: Any) -> Optional[bool]:
        try:
            import win32gui
        except ImportError:
            logger.debug("window_title_contains verifier: pywin32 unavailable, skipping check")
            return None

        wanted = [k.lower() for k in keywords]
        found = False

        def _enum_handler(hwnd, _):
            nonlocal found
            if found or not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd).lower()
            if title and any(w in title for w in wanted):
                found = True

        try:
            win32gui.EnumWindows(_enum_handler, None)
        except Exception as exc:
            logger.debug("window_title_contains verifier failed: %s", exc)
            return None
        return found

    return _verify


def window_title_absent(*keywords: str) -> VerifyFn:
    """Verifier for CLOSE/STOP-style actions: True if NONE of `keywords`
    appear in any visible window title (i.e. it's confirmed gone), False if
    one is still visible, None if the check can't run at all here. This is
    window_title_contains with negated True/False semantics — kept as its
    own function rather than a generic "not()" wrapper so the None-passthrough
    (can't check != confirmed gone) stays explicit and easy to read at the
    call site.
    """
    _presence_check = window_title_contains(*keywords)

    def _verify(args: Dict[str, Any], result: Any) -> Optional[bool]:
        present = _presence_check(args, result)
        if present is None:
            return None
        return not present

    return _verify


def any_of(*verifiers: VerifyFn) -> VerifyFn:
    """Combinator: True if ANY sub-verifier says True; False only if ALL say
    False; otherwise None (mixed signal / genuinely unknown)."""

    def _verify(args: Dict[str, Any], result: Any) -> Optional[bool]:
        outcomes = [v(args, result) for v in verifiers]
        if any(o is True for o in outcomes):
            return True
        if outcomes and all(o is False for o in outcomes):
            return False
        return None

    return _verify


def run_with_verification(
    call: Callable[[], Any],
    verify: Optional[VerifyFn],
    args: Dict[str, Any],
    max_retries: int = 0,
    retry_delay: float = 1.5,
) -> Tuple[Any, Optional[bool]]:
    """Call `call()` (a zero-arg thunk that re-invokes the tool handler),
    then check `verify(args, result)` if one was declared. Retries the WHOLE
    action (not just the check) up to `max_retries` times if verification
    comes back definitively False — e.g. "camera.open" reported success but
    no Camera window actually appeared, so try launching it again rather
    than trusting the first report.

    Returns (result, verified):
      verified is True/False if a verifier ran and gave a definite answer,
      or None if there was no verifier, or it genuinely couldn't tell.
    """

    attempts = 0
    result = None
    verified: Optional[bool] = None

    while True:
        result = call()
        attempts += 1

        if verify is None:
            return result, None

        if not getattr(result, "success", False):
            # The action itself already reported failure — nothing to verify,
            # that's a straightforward failure as-is.
            return result, False

        time.sleep(retry_delay)  # give the OS/app a moment to actually reflect the change
        verified = verify(args, result)

        if verified is not False or attempts > max_retries:
            return result, verified

        logger.debug(
            "Verification failed (attempt %d/%d), retrying the action...",
            attempts, max_retries + 1,
        )
