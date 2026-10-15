"""
Tests for v1.2.1 Bug 4: alarm_tool.py's honesty fix (set_alarm/list_alarms
messages clarify these are Task-Scheduler-based reminders, not native
Windows Alarms) and the new alarm.open action.
"""
import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tools import alarm_tool  # noqa: E402


class TestSetAlarmHonesty:
    def test_success_message_clarifies_not_native_alarms(self):
        fake_result = MagicMock(returncode=0, stderr="")
        with patch.object(alarm_tool.subprocess, "run", return_value=fake_result):
            result = alarm_tool.set_alarm("07:00")
        assert result.success
        assert "task scheduler" in result.message.lower()
        assert "won't show up" in result.message.lower() or "won't appear" in result.message.lower()

    def test_failure_message_unaffected(self):
        fake_result = MagicMock(returncode=1, stderr="access denied")
        with patch.object(alarm_tool.subprocess, "run", return_value=fake_result):
            result = alarm_tool.set_alarm("07:00")
        assert not result.success
        assert "access denied" in result.message.lower()


class TestListAlarmsHonesty:
    def test_message_clarifies_not_native_alarms_when_alarms_exist(self):
        with patch.object(alarm_tool, "_list_alarm_tasks", return_value=[{"task_name": "x", "time": "07:00"}]):
            result = alarm_tool.list_alarms()
        assert result.success
        assert "task scheduler" in result.message.lower()

    def test_empty_list_message_unaffected(self):
        with patch.object(alarm_tool, "_list_alarm_tasks", return_value=[]):
            result = alarm_tool.list_alarms()
        assert result.success
        assert "don't have any alarms" in result.message.lower()


class TestOpenAlarmsApp:
    def test_launches_via_aumid_not_generic_ms_clock_uri(self):
        with patch.object(alarm_tool.subprocess, "run") as mock_run:
            result = alarm_tool.open_alarms_app()
        assert result.success
        args = mock_run.call_args[0][0]
        assert args[0] == "explorer.exe"
        assert "Microsoft.WindowsAlarms" in args[1]

    def test_message_clarifies_reminders_are_separate(self):
        with patch.object(alarm_tool.subprocess, "run"):
            result = alarm_tool.open_alarms_app()
        assert "separate" in result.message.lower()

    def test_launch_failure_reported_cleanly(self):
        with patch.object(alarm_tool.subprocess, "run", side_effect=OSError("not found")):
            result = alarm_tool.open_alarms_app()
        assert not result.success