"""
Browser Session Manager
========================
A single, persistent, dedicated automation browser profile — reused across
every tool/call in this process — instead of "Selenium launches a brand
new temporary profile every call."

BROWSER-INDEPENDENT: this module does NOT hard-require Chrome. It
auto-detects whichever supported Chromium-based browser is actually
installed (Chrome, then Edge, in that preference order — overridable via
the PRERNA_BROWSER_ENGINE env var) and automates THAT one. Nothing about
which browser you personally have open, or prefer for everyday browsing,
matters — automation runs in its own separate, dedicated profile/window
regardless.

(Firefox isn't supported here: unlike Chromium-based browsers, Selenium
can't cleanly attach to an already-running Firefox instance the way it
can via Chrome DevTools Protocol's `debugger_address` — Firefox automation
would need a materially different, less reliable approach. If that's ever
actually needed, it should be built as its own explicit path rather than
folded into this one.)

DESIGN HISTORY / WHY A DEDICATED PROFILE:
An earlier version of this module tried to attach to the user's actual,
everyday browser profile (the one showing their normal browsing, and often
also Prerna's own frontend UI). That meant that whenever the browser was
already running WITHOUT remote debugging enabled — the normal state of a
regular window — this module would kill EVERY process of that browser on
the machine (there's no way to tell "the user's everyday window" apart
from "the window showing Prerna's own UI" from the outside) and relaunch.
In practice this meant asking Prerna to "play a song" while her own UI was
open would silently kill the tab she's running in.

This version avoids that failure mode entirely by giving automation its
OWN dedicated, separate profile — a persistent folder on disk, not a temp
directory — that nothing else ever touches:

  - It never needs to close or restart any window the user is actually
    using (their everyday browsing, Prerna's own UI, anything else).
  - It's a REAL, persistent profile: the first time it's used, the user
    signs into YouTube/Gmail/etc. in it once; from then on, cookies,
    logins, and history in THAT profile persist across every future
    Prerna session — same "not a fresh throwaway browser every time"
    benefit, just scoped to a profile dedicated to automation rather than
    the user's literal daily-driver profile.
  - "Restart if crashed" only ever targets processes launched from THIS
    specific automation profile directory (checked via each process's own
    command line), never any other window on the machine, on any engine.

Honest trade-off, stated plainly: this profile starts out NOT signed into
anything. The first automation run per engine will open a fresh-looking
window; the user should sign in inside it once. It remembers from then on.

How the underlying attach mechanism works:

Chromium-based browsers (Chrome and Edge both) have a "remote debugging"
mode (`--remote-debugging-port=9222`) exposing a local control API.
Selenium can attach to an already-running instance in this mode via
`options.debugger_address`, instead of spawning a new process itself. That
flag can only be set at launch, so the manager's job is:

  1. Is a debug-enabled browser already reachable on 127.0.0.1:9222?
     -> just attach. Nothing else to do.
  2. Otherwise -> launch the detected engine fresh, using the dedicated
     automation profile directory, with debugging enabled from the start.

Nothing in this module ever enumerates or terminates browser processes
that aren't running from the dedicated automation profile.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)

DEBUG_PORT = 9222
DEBUG_ADDRESS = f"127.0.0.1:{DEBUG_PORT}"

# Preference order when no PRERNA_BROWSER_ENGINE override is set. Both are
# Chromium-based and support attaching via remote debugging the same way;
# Chrome is tried first only because it's the more common default, not
# because anything here actually requires it specifically.
_ENGINES = [
    {
        "name": "chrome",
        "display_name": "Google Chrome",
        "process_name": "chrome.exe",
        "exe_candidates": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ],
        "exe_localappdata_suffix": ("Google", "Chrome", "Application", "chrome.exe"),
        "webdriver_attr": "Chrome",
        "options_module": "selenium.webdriver.chrome.options",
    },
    {
        "name": "edge",
        "display_name": "Microsoft Edge",
        "process_name": "msedge.exe",
        "exe_candidates": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
        "exe_localappdata_suffix": ("Microsoft", "Edge", "Application", "msedge.exe"),
        "webdriver_attr": "Edge",
        "options_module": "selenium.webdriver.edge.options",
    },
]

_AUTOMATION_PROFILE_MARKER = "PrernaAutomationProfile"


def _engine_by_name(name: str) -> Optional[dict]:
    name = (name or "").strip().lower()
    return next((e for e in _ENGINES if e["name"] == name), None)


def _find_engine() -> Optional[dict]:
    """Resolve which browser engine to automate, honoring an explicit
    PRERNA_BROWSER_ENGINE override first, then auto-detecting whichever
    supported engine is actually installed. Returns an engine dict (with
    a resolved 'exe_path' key added) or None if nothing usable is found."""
    forced_name = os.environ.get("PRERNA_BROWSER_ENGINE", "").strip().lower()
    if forced_name:
        forced = _engine_by_name(forced_name)
        if not forced:
            logger.warning(
                "PRERNA_BROWSER_ENGINE=%r isn't a supported engine (chrome/edge) — ignoring override.",
                forced_name,
            )
        else:
            exe = _find_engine_exe(forced)
            if exe:
                return {**forced, "exe_path": exe}
            logger.warning(
                "PRERNA_BROWSER_ENGINE=%r was set but %s wasn't found installed — falling back to auto-detect.",
                forced_name, forced["display_name"],
            )

    for engine in _ENGINES:
        exe = _find_engine_exe(engine)
        if exe:
            return {**engine, "exe_path": exe}

    return None


def _find_engine_exe(engine: dict) -> Optional[str]:
    candidates = list(engine["exe_candidates"])
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if local_appdata:
        candidates.append(str(Path(local_appdata).joinpath(*engine["exe_localappdata_suffix"])))
    for path in candidates:
        if Path(path).exists():
            return path
    return None


def _automation_user_data_dir(engine_name: str) -> Path:
    """A dedicated, persistent profile folder used ONLY for automation of
    the given engine — deliberately separate per engine (Chrome and Edge
    profile formats aren't interchangeable) and deliberately NOT the
    user's everyday profile, so this module can never collide with (or
    need to close) any window the user is actually using. Created on
    first use if it doesn't exist yet; everything written into it
    persists across restarts exactly like a normal browser profile does."""
    local_appdata = os.environ.get("LOCALAPPDATA", "") or str(Path.home())
    path = Path(local_appdata) / f"{_AUTOMATION_PROFILE_MARKER}-{engine_name}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _debug_port_reachable(timeout: float = 1.0) -> bool:
    """True if a browser is already listening with remote debugging on
    our port — the cheap, no-Selenium-needed check before doing anything
    more invasive. Engine-agnostic: the CDP JSON endpoint looks the same
    whether it's Chrome or Edge underneath."""
    try:
        import requests
        resp = requests.get(f"http://{DEBUG_ADDRESS}/json/version", timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def _automation_processes(engine: dict):
    """Only the process(es) launched from OUR dedicated automation profile
    for this specific engine — identified by checking each process's own
    command line for our profile path, never matched by process name
    alone. This is the key safety property of this module: it can never
    mistake the user's everyday browser window (or the window showing
    Prerna's own UI) for an automation process, so it can never
    accidentally terminate them."""
    try:
        import psutil
    except ImportError:
        logger.warning("psutil not available — cannot inspect browser processes.")
        return []

    marker = str(_automation_user_data_dir(engine["name"]))
    matches = []
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            if (proc.info.get("name") or "").lower() != engine["process_name"]:
                continue
            cmdline = proc.info.get("cmdline") or []
            if any(marker in arg for arg in cmdline):
                matches.append(proc)
        except Exception:
            continue
    return matches


def _terminate_automation_processes(engine: dict, timeout: float = 8.0) -> None:
    """Force-close ONLY our dedicated automation process(es) for this
    engine — used for crash recovery, never touches any other window on
    any engine. Waits for actual process exit (not a fixed sleep) and
    cleans up the browser's own singleton lock files afterward so the
    next launch isn't silently handed off to a now-dead process."""
    try:
        import psutil
    except ImportError:
        return

    procs = _automation_processes(engine)
    if not procs:
        _clear_singleton_lock(engine)
        return

    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass

    _, alive = psutil.wait_procs(procs, timeout=timeout)
    if alive:
        for p in alive:
            try:
                p.kill()
            except Exception:
                pass
        psutil.wait_procs(alive, timeout=3.0)

    _clear_singleton_lock(engine)
    _mark_profile_exit_clean(engine)


def _clear_singleton_lock(engine: dict) -> None:
    """Remove the browser's own "another instance owns this profile" lock
    files from OUR dedicated automation profile, if still present after
    confirming its process is actually gone. A stale lock silently breaks
    the next launch — the browser hands its args off to the (now-dead)
    old process instead of becoming a real new debug-enabled instance."""
    user_data_dir = _automation_user_data_dir(engine["name"])
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        path = user_data_dir / name
        try:
            if path.exists() or path.is_symlink():
                path.unlink()
        except Exception as exc:
            logger.debug("Couldn't remove stale %s (%s) — usually harmless.", name, exc)


def _mark_profile_exit_clean(engine: dict) -> None:
    """A force-kill reads as a crash to the browser's own bookkeeping,
    which triggers a "didn't shut down correctly, restore pages?" popup on
    next launch — patch the automation profile's exit_type back to normal
    to avoid that popup blocking automation."""
    user_data_dir = _automation_user_data_dir(engine["name"])
    for prefs_path in user_data_dir.glob("*/Preferences"):
        try:
            with open(prefs_path, "r", encoding="utf-8") as f:
                prefs = json.load(f)
            profile_section = prefs.get("profile")
            if not isinstance(profile_section, dict):
                continue
            if profile_section.get("exit_type") == "Normal":
                continue
            profile_section["exit_type"] = "Normal"
            profile_section["exit_ok"] = True
            with open(prefs_path, "w", encoding="utf-8") as f:
                json.dump(prefs, f)
        except Exception as exc:
            logger.debug("Couldn't mark %s as cleanly exited (%s).", prefs_path, exc)


class ChromeSessionManager:
    """One shared, persistent, dedicated-automation-profile browser
    session for every tool that needs browser automation. Auto-detects
    whichever supported engine (Chrome or Edge) is installed and never
    touches the user's everyday browser window or any window running
    Prerna's own UI — those are simply invisible to this module, since it
    only ever launches/attaches/terminates its own separate profile.

    (Class name kept as ChromeSessionManager for import compatibility with
    existing tools — it's no longer Chrome-specific internally.)
    """

    def __init__(self) -> None:
        self._driver = None
        self._engine: Optional[dict] = None
        self.last_error: Optional[str] = None

    # ── Public API ──────────────────────────────────────────────────────

    def get_browser(self):
        """The single entry point tools should call. Returns a live
        Selenium driver attached to the dedicated automation browser,
        starting or reattaching it if necessary. Returns None (with
        `.last_error` set) only if no supported browser can be reached."""
        return self.ensure_browser_running()

    def ensure_browser_running(self):
        if self._driver is not None and self._is_alive(self._driver):
            return self._driver

        self._driver = None  # drop anything stale/dead first

        if self._engine is None:
            self._engine = _find_engine()
            if self._engine is None:
                self.last_error = (
                    "No supported browser found — install Google Chrome or "
                    "Microsoft Edge (or set PRERNA_BROWSER_ENGINE to one you "
                    "have) to enable browser automation."
                )
                logger.error(self.last_error)
                return None
            logger.info("Automation engine: %s", self._engine["display_name"])

        if _debug_port_reachable():
            driver = self.attach_existing_session()
            if driver:
                return driver
            # Something is listening on the port but didn't respond
            # usefully (e.g. a half-dead process) — clear it out and
            # launch fresh, rather than looping on a broken attach.
            _terminate_automation_processes(self._engine)

        driver = self.launch_browser()
        if driver:
            return driver

        # One automatic retry: the most common cause of a failed first
        # attempt is a stale singleton lock from an earlier crash — a
        # second clean terminate+relaunch cycle resolves it.
        logger.warning("First launch attempt failed — retrying once after a clean terminate.")
        _terminate_automation_processes(self._engine)
        return self.launch_browser()

    def attach_existing_session(self):
        """Attach Selenium to an already-running, debug-enabled browser —
        never launches a new process. Uses whichever Selenium driver class
        matches the resolved engine (Chrome vs Edge use different driver
        binaries even though both speak the same debugging protocol)."""
        if self._engine is None:
            self._engine = _find_engine()
            if self._engine is None:
                self.last_error = "No supported browser found."
                return None
        try:
            from selenium import webdriver
            import importlib

            options_module = importlib.import_module(self._engine["options_module"])
            options = options_module.Options()
            options.debugger_address = DEBUG_ADDRESS

            driver_class = getattr(webdriver, self._engine["webdriver_attr"])
            driver = driver_class(options=options)
            _ = driver.window_handles  # confirm it actually responds
            self._driver = driver
            self.last_error = None
            logger.info(
                "Attached to existing %s automation session on %s.",
                self._engine["display_name"], DEBUG_ADDRESS,
            )
            return driver
        except Exception as exc:
            self.last_error = f"Couldn't attach to existing browser session: {exc}"
            logger.warning(self.last_error)
            return None

    def launch_browser(self):
        """Launch the resolved engine fresh, WITH debugging enabled, using
        the dedicated automation profile — never the user's everyday
        profile, never Selenium's own throwaway temp profile."""
        if self._engine is None:
            self._engine = _find_engine()
        if self._engine is None:
            self.last_error = "No supported browser found."
            return None

        engine = self._engine
        user_data_dir = _automation_user_data_dir(engine["name"])
        launch_args = [
            engine["exe_path"],
            f"--remote-debugging-port={DEBUG_PORT}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-session-crashed-bubble",
            "--disable-features=InfiniteSessionRestore",
        ]
        logger.info("Launching dedicated automation %s profile: %s", engine["display_name"], user_data_dir)

        try:
            subprocess.Popen(launch_args)
        except Exception as exc:
            self.last_error = f"Failed to launch {engine['display_name']}: {exc}"
            logger.error(self.last_error)
            return None

        # Poll for the debug port to come up rather than a fixed sleep —
        # startup time varies with system load / extension count.
        deadline = time.time() + 15.0
        while time.time() < deadline:
            if _debug_port_reachable():
                return self.attach_existing_session()
            time.sleep(0.4)

        self.last_error = f"{engine['display_name']} launched but the debugging port never came up in time."
        logger.error(self.last_error)
        return None

    def restart_browser(self):
        """Force-quit and relaunch the automation browser — used for crash
        recovery. Only ever targets our own dedicated automation profile's
        process(es), never any other window on any engine."""
        self._driver = None
        if self._engine is None:
            self._engine = _find_engine()
        if self._engine:
            _terminate_automation_processes(self._engine)
        time.sleep(1.0)
        return self.launch_browser()

    def close_browser(self) -> None:
        """Release our handle WITHOUT closing the automation browser
        window. Deliberately does NOT call driver.quit() — quit() would
        close every tab/window in that browser, which isn't necessary
        just to stop tracking it from this process; the window can simply
        keep running (or the user can close it by hand) and a later call
        will reattach to it via the debug port if it's still open."""
        self._driver = None

    # ── Internal ────────────────────────────────────────────────────────

    @staticmethod
    def _is_alive(driver) -> bool:
        try:
            _ = driver.window_handles
            return True
        except Exception:
            return False


def open_in_new_tab(driver, url: str) -> None:
    """Navigate to `url` in a brand-new tab and switch focus to it, rather
    than hijacking whatever tab was last active in the automation window."""
    driver.switch_to.new_window("tab")
    driver.get(url)


_session: ChromeSessionManager | None = None


def get_chrome_session() -> ChromeSessionManager:
    """Process-wide singleton — every tool shares the same session,
    regardless of which underlying engine ends up being used."""
    global _session
    if _session is None:
        _session = ChromeSessionManager()
    return _session