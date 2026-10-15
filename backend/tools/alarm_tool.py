"""
Alarm / Reminder / Timer tool
==============================
- Alarms: scheduled via Windows Task Scheduler (`schtasks`), so they fire
  even if this backend isn't running at the time. Each alarm gets a task
  named "Prerna_Alarm_<HHMM>_<id>" so it can be listed/cancelled later,
  individually or all at once, and can be one-off or daily recurring.
- Timers/reminders: short countdowns handled in-process (thread + popup),
  since they're meant to fire while you're actively using Prerna anyway.

Security note: `label` is free-text (from voice/planner args) that gets
embedded in a PowerShell single-quoted string. PowerShell only treats a
doubled single-quote ('') as an escape inside single-quoted strings — no
other character breaks out of one — so `_ps_escape()` doubles any single
quotes and strips newlines/control characters before the label ever
reaches the command. Previously the label was interpolated raw, so a
label containing a single quote could break out of the string and run
arbitrary PowerShell (e.g. deleting files). Fixed here.

v1.2.1 Bug 4 note: alarms set here are Prerna's OWN reminder popups (a
scheduled task that shows a PowerShell MessageBox at the target time) —
they deliberately do NOT use, and will never appear in, the native
Windows Alarms & Clock app. Both `schtasks /create` and `schtasks /query`
confirm the tasks genuinely exist and genuinely fire; this was never a
false-success bug. It WAS, however, never communicated to the user, who
reasonably checked the native Clock app and concluded alarms were broken
when they didn't show up there. set_alarm/list_alarms' messages below say
this explicitly now.
"""

from __future__ import annotations

import re
import subprocess
import threading
import uuid
from typing import Dict, Optional

from agent.registry import ToolResult, action
from config.settings import ALARM_TASK_PREFIX as _TASK_PREFIX

_active_timers: Dict[str, threading.Timer] = {}

TOOL_DESCRIPTION = "Set/cancel/list alarms (one-off or daily), and set short reminders or countdown timers."

_MAX_LABEL_LEN = 80


def _validate_time(time_str: str) -> str:
    if not re.match(r"^([01]?\d|2[0-3]):[0-5]\d$", time_str.strip()):
        raise ValueError(f"'{time_str}' doesn't look like a HH:MM time.")
    return time_str.strip()


def _ps_escape(label: str) -> str:
    """Make free-text safe to embed inside a PowerShell single-quoted string.

    Inside '...' PowerShell only treats a doubled '' as an escaped literal
    quote; nothing else (backticks, $, ;) is special. So escaping is just:
    strip newlines/control chars (they have no business in a messagebox
    title anyway), cap length, and double any single quotes.
    """
    label = (label or "").strip() or "Alarm"
    label = re.sub(r"[\r\n\t\x00-\x1f]", " ", label)  # no control chars
    label = label[:_MAX_LABEL_LEN]
    return label.replace("'", "''")


def _messagebox_command(label: str, title: str) -> str:
    safe_label = _ps_escape(label)
    safe_title = _ps_escape(title)
    return (
        "Add-Type -AssemblyName System.Windows.Forms; "
        f"[System.Windows.Forms.MessageBox]::Show('{safe_label}', '{safe_title}')"
    )


def _alarm_task_name(hhmm: str) -> str:
    task_id = uuid.uuid4().hex[:8]
    return f"{_TASK_PREFIX}{hhmm.replace(':', '')}_{task_id}"


def _list_alarm_tasks() -> list[dict[str, str]]:
    """Return [{"task_name": ..., "time": ...}, ...] for every Prerna alarm task."""
    result = subprocess.run(
        ["schtasks", "/query", "/fo", "csv", "/nh"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return []

    tasks = []
    for line in result.stdout.splitlines():
        if _TASK_PREFIX not in line:
            continue
        name = line.split(",")[0].strip('"').lstrip("\\")
        # name looks like "Prerna_Alarm_0700_a1b2c3d4"
        match = re.search(r"_(\d{4})_[0-9a-f]{8}$", name)
        time_str = f"{match.group(1)[:2]}:{match.group(1)[2:]}" if match else "?"
        tasks.append({"task_name": name, "time": time_str})
    return tasks


@action(
    "alarm", "set", "Set an alarm for a specific time (HH:MM, 24h). Optionally recurring daily.",
    required_args=["time"], tool_description=TOOL_DESCRIPTION,
)
def set_alarm(time: str, label: str = "Alarm", recurring: bool = False) -> ToolResult:
    hhmm = _validate_time(time)
    task_name = _alarm_task_name(hhmm)
    command = f'powershell -Command "{_messagebox_command(label, "Prerna Alarm")}"'

    schedule_args = ["/sc", "daily"] if recurring else ["/sc", "once"]

    result = subprocess.run(
        [
            "schtasks", "/create", "/tn", task_name, "/tr", command,
            *schedule_args, "/st", hhmm, "/f",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    if result.returncode != 0:
        return ToolResult(False, f"Couldn't set the alarm: {result.stderr.strip() or 'unknown error'}")

    when = "every day" if recurring else "once"
    return ToolResult(
        True,
        f"Alarm set for {hhmm} ({when}) — I'll pop up a reminder here at that time. "
        "Note: this is my own reminder (via Windows Task Scheduler), not the native "
        "Windows Alarms app, so it won't show up if you check Clock.",
        data={"task_name": task_name},
    )


@action("alarm", "list", "List all alarms Prerna has set.")
def list_alarms() -> ToolResult:
    tasks = _list_alarm_tasks()
    if not tasks:
        return ToolResult(True, "You don't have any alarms set with me.")
    times = ", ".join(t["time"] for t in tasks)
    return ToolResult(
        True,
        f"You have {len(tasks)} alarm(s) set with me: {times}. "
        "These are my own reminders (via Task Scheduler) — you won't see them in the "
        "native Windows Alarms app.",
        data={"alarms": tasks},
    )


@action(
    "alarm", "cancel", "Cancel one alarm, by time if given (e.g. '07:00'); "
    "if you only have one alarm set, cancels that one without needing a time.",
)
def cancel_alarm(time: Optional[str] = None) -> ToolResult:
    tasks = _list_alarm_tasks()
    if not tasks:
        return ToolResult(True, "You don't have any alarms set.")

    if time:
        hhmm = _validate_time(time)
        matches = [t for t in tasks if t["time"] == hhmm]
    elif len(tasks) == 1:
        matches = tasks
    else:
        times = ", ".join(t["time"] for t in tasks)
        return ToolResult(
            False,
            f"You have {len(tasks)} alarms ({times}) — which time should I cancel?",
        )

    if not matches:
        return ToolResult(False, f"No alarm found for {time}.")

    for t in matches:
        subprocess.run(["schtasks", "/delete", "/tn", t["task_name"], "/f"], capture_output=True, timeout=10)

    cancelled_times = ", ".join(t["time"] for t in matches)
    return ToolResult(True, f"Cancelled the {cancelled_times} alarm.")


@action("alarm", "cancel_all", "Cancel every alarm Prerna has set.")
def cancel_all_alarms() -> ToolResult:
    tasks = _list_alarm_tasks()
    for t in tasks:
        subprocess.run(["schtasks", "/delete", "/tn", t["task_name"], "/f"], capture_output=True, timeout=10)
    return ToolResult(True, f"Cancelled {len(tasks)} alarm(s)." if tasks else "You don't have any alarms set.")


# ── v1.2.1 Bug 4: a dedicated way to open the real Windows Alarms app ────
#
# Previously "open alarm"/"open clock" routed through system_tool.open_app,
# which maps both "clock" and "alarms" to the generic `start ms-clock:`
# URI — that opens the Clock app, but on whatever tab it last had open
# (often Timer), not specifically Alarms. This uses the Alarms & Clock
# app's AUMID directly, which is the best-known way to target a specific
# tab in that app.
#
# CAVEAT (unconfirmed — verify on real Windows): Windows' AUMID launch
# mechanism for this app is not well documented publicly for landing on a
# specific tab; it's the best-known approach, not a guaranteed one. If it
# still lands on the wrong tab, this needs revisiting with the real
# behavior observed.
_ALARMS_APP_AUMID = r"shell:appsFolder\Microsoft.WindowsAlarms_8wekyb3d8bbwe!App"


@action("alarm", "open", "Open the native Windows Alarms & Clock app.")
def open_alarms_app() -> ToolResult:
    try:
        subprocess.run(["explorer.exe", _ALARMS_APP_AUMID], timeout=10)
    except Exception as exc:
        return ToolResult(False, f"Couldn't open the Alarms app: {exc}")
    return ToolResult(
        True,
        "Opened the Windows Alarms & Clock app. Note: alarms I set for you are separate "
        "reminders and won't appear there — say 'list alarms' to see those.",
    )


@action(
    "timer",
    "set",
    "Set a countdown timer (in minutes) that pops up when it's done.",
    required_args=["minutes"],
    tool_description="Short in-app countdown timers/reminders (while Prerna is running).",
)
def set_timer(minutes: float, label: str = "Timer") -> ToolResult:
    seconds = float(minutes) * 60
    timer_id = uuid.uuid4().hex[:8]

    def _fire():
        try:
            subprocess.run(
                ["powershell", "-Command", _messagebox_command(label, "Prerna Timer")],
                timeout=15,
            )
        except Exception:
            pass
        _active_timers.pop(timer_id, None)

    t = threading.Timer(seconds, _fire)
    t.daemon = True
    t.start()
    _active_timers[timer_id] = t

    return ToolResult(True, f"Timer set for {minutes} minute(s).", data={"timer_id": timer_id})


@action("timer", "cancel_all", "Cancel every active in-app timer.")
def cancel_all_timers() -> ToolResult:
    count = len(_active_timers)
    for t in _active_timers.values():
        t.cancel()
    _active_timers.clear()
    return ToolResult(True, f"Cancelled {count} timer(s)." if count else "No active timers.")