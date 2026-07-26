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
    return ToolResult(True, f"Alarm set for {hhmm} ({when}).", data={"task_name": task_name})


@action("alarm", "list", "List all alarms Prerna has set.")
def list_alarms() -> ToolResult:
    tasks = _list_alarm_tasks()
    if not tasks:
        return ToolResult(True, "You don't have any alarms set.")
    times = ", ".join(t["time"] for t in tasks)
    return ToolResult(True, f"You have {len(tasks)} alarm(s) set: {times}.", data={"alarms": tasks})


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