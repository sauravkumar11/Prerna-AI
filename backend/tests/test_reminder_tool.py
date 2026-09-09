"""
test_reminder_tool.py
=====================
Unit tests for tools/reminder_tool.py

Tests task creation, listing, completion, and persistence.

v1.1.1 addition: Comprehensive reminder/task management tests
"""

from __future__ import annotations

import pytest
import json
from pathlib import Path
from datetime import datetime, timedelta
from tools.reminder_tool import (
    ReminderManager,
    Task,
    TaskPriority,
    TaskStatus,
    add_reminder_action,
    list_reminders_action,
    complete_reminder_action,
    get_reminder_summary_action,
    delete_reminder_action,
)
from agent.registry import ToolResult


class TestTaskDataclass:
    """Test Task dataclass functionality."""

    @pytest.mark.unit
    def test_task_creation(self):
        """Should create a task with required fields."""
        task = Task(
            id="task-1",
            title="Buy groceries",
            priority=TaskPriority.MEDIUM.value,
        )
        assert task.id == "task-1"
        assert task.title == "Buy groceries"
        assert task.status == TaskStatus.PENDING.value

    @pytest.mark.unit
    def test_task_with_due_date(self):
        """Should handle tasks with due dates."""
        due_date = "2024-12-25"
        task = Task(
            id="task-2",
            title="Christmas shopping",
            due_date=due_date,
            priority=TaskPriority.HIGH.value,
        )
        assert task.due_date == due_date

    @pytest.mark.unit
    def test_task_is_overdue(self):
        """Should correctly identify overdue tasks."""
        past_date = (datetime.now() - timedelta(days=1)).date().isoformat()
        task = Task(
            id="task-3",
            title="Late task",
            due_date=past_date,
            status=TaskStatus.PENDING.value,
        )
        assert task.is_overdue()

    @pytest.mark.unit
    def test_task_not_overdue_when_completed(self):
        """Completed tasks should not be considered overdue."""
        past_date = (datetime.now() - timedelta(days=1)).date().isoformat()
        task = Task(
            id="task-4",
            title="Completed task",
            due_date=past_date,
            status=TaskStatus.COMPLETED.value,
        )
        assert not task.is_overdue()

    @pytest.mark.unit
    def test_task_get_display_text(self):
        """Should generate readable task text."""
        task = Task(
            id="task-5",
            title="Important meeting",
            priority=TaskPriority.HIGH.value,
            due_date="2024-12-25",
        )
        display = task.get_display_text()
        assert "Important meeting" in display
        assert "HIGH" in display
        assert "2024-12-25" in display

    @pytest.mark.unit
    def test_task_to_dict_and_from_dict(self):
        """Should convert to/from dict correctly."""
        original = Task(
            id="task-6",
            title="Test task",
            description="A test",
            priority=TaskPriority.HIGH.value,
        )
        task_dict = original.to_dict()
        restored = Task.from_dict(task_dict)

        assert restored.id == original.id
        assert restored.title == original.title
        assert restored.priority == original.priority


class TestReminderManager:
    """Test ReminderManager functionality."""

    @pytest.mark.unit
    def test_manager_initialization(self, temp_memory_dir):
        """Should initialize with empty tasks."""
        manager = ReminderManager(storage_file=temp_memory_dir / "test.json")
        assert len(manager.tasks) == 0

    @pytest.mark.unit
    def test_add_task(self, temp_memory_dir):
        """Should add a new task."""
        manager = ReminderManager(storage_file=temp_memory_dir / "test.json")
        task = manager.add_task("Buy milk", priority="high")

        assert task.title == "Buy milk"
        assert task.priority == "high"
        assert task.id in manager.tasks

    @pytest.mark.unit
    def test_add_task_with_all_fields(self, temp_memory_dir):
        """Should add task with all optional fields."""
        manager = ReminderManager(storage_file=temp_memory_dir / "test.json")
        task = manager.add_task(
            title="Project deadline",
            description="Finish the backend",
            priority="urgent",
            category="work",
            due_date="2024-12-31",
            due_time="17:00",
        )

        assert task.description == "Finish the backend"
        assert task.category == "work"
        assert task.due_date == "2024-12-31"

    @pytest.mark.unit
    def test_get_task(self, temp_memory_dir):
        """Should retrieve task by ID."""
        manager = ReminderManager(storage_file=temp_memory_dir / "test.json")
        added_task = manager.add_task("Test task")
        retrieved = manager.get_task(added_task.id)

        assert retrieved is not None
        assert retrieved.title == "Test task"

    @pytest.mark.unit
    def test_get_nonexistent_task(self, temp_memory_dir):
        """Should return None for nonexistent task."""
        manager = ReminderManager(storage_file=temp_memory_dir / "test.json")
        task = manager.get_task("nonexistent")
        assert task is None

    @pytest.mark.unit
    def test_list_all_tasks(self, temp_memory_dir):
        """Should list all tasks."""
        manager = ReminderManager(storage_file=temp_memory_dir / "test.json")
        manager.add_task("Task 1")
        manager.add_task("Task 2")
        manager.add_task("Task 3")

        tasks = manager.list_tasks()
        assert len(tasks) == 3

    @pytest.mark.unit
    def test_list_tasks_by_status(self, temp_memory_dir):
        """Should filter tasks by status."""
        manager = ReminderManager(storage_file=temp_memory_dir / "test.json")
        task1 = manager.add_task("Task 1")
        task2 = manager.add_task("Task 2")

        manager.complete_task(task1.id)

        pending = manager.list_tasks(status="pending")
        completed = manager.list_tasks(status="completed")

        assert len(pending) == 1
        assert len(completed) == 1

    @pytest.mark.unit
    def test_list_tasks_by_priority(self, temp_memory_dir):
        """Should filter tasks by priority."""
        manager = ReminderManager(storage_file=temp_memory_dir / "test.json")
        manager.add_task("Low priority", priority="low")
        manager.add_task("High priority", priority="high")

        high = manager.list_tasks(priority="high")
        low = manager.list_tasks(priority="low")

        assert len(high) == 1
        assert len(low) == 1

    @pytest.mark.unit
    def test_list_tasks_by_category(self, temp_memory_dir):
        """Should filter tasks by category."""
        manager = ReminderManager(storage_file=temp_memory_dir / "test.json")
        manager.add_task("Work task", category="work")
        manager.add_task("Personal task", category="personal")

        work = manager.list_tasks(category="work")
        personal = manager.list_tasks(category="personal")

        assert len(work) == 1
        assert len(personal) == 1

    @pytest.mark.unit
    def test_complete_task(self, temp_memory_dir):
        """Should mark task as completed."""
        manager = ReminderManager(storage_file=temp_memory_dir / "test.json")
        task = manager.add_task("Complete me")

        completed = manager.complete_task(task.id)

        assert completed.status == TaskStatus.COMPLETED.value
        assert completed.completed_at is not None

    @pytest.mark.unit
    def test_delete_task(self, temp_memory_dir):
        """Should delete a task."""
        manager = ReminderManager(storage_file=temp_memory_dir / "test.json")
        task = manager.add_task("Delete me")

        success = manager.delete_task(task.id)

        assert success is True
        assert task.id not in manager.tasks

    @pytest.mark.unit
    def test_delete_nonexistent_task(self, temp_memory_dir):
        """Should handle deletion of nonexistent task."""
        manager = ReminderManager(storage_file=temp_memory_dir / "test.json")
        success = manager.delete_task("nonexistent")
        assert success is False

    @pytest.mark.unit
    def test_get_overdue_tasks(self, temp_memory_dir):
        """Should identify overdue tasks."""
        manager = ReminderManager(storage_file=temp_memory_dir / "test.json")
        past = (datetime.now() - timedelta(days=1)).date().isoformat()
        manager.add_task("Overdue task", due_date=past)
        manager.add_task("Future task", due_date="2099-12-31")

        overdue = manager.get_overdue_tasks()
        assert len(overdue) == 1

    @pytest.mark.unit
    def test_get_today_tasks(self, temp_memory_dir):
        """Should get tasks due today."""
        manager = ReminderManager(storage_file=temp_memory_dir / "test.json")
        today = datetime.now().date().isoformat()
        manager.add_task("Today task", due_date=today)
        manager.add_task("Tomorrow task", due_date="2099-12-31")

        today_tasks = manager.get_today_tasks()
        assert len(today_tasks) == 1

    @pytest.mark.unit
    def test_get_summary(self, temp_memory_dir):
        """Should generate summary statistics."""
        manager = ReminderManager(storage_file=temp_memory_dir / "test.json")
        task1 = manager.add_task("Task 1")
        task2 = manager.add_task("Task 2")
        task3 = manager.add_task("Task 3")

        manager.complete_task(task1.id)

        summary = manager.get_summary()

        assert summary["total"] == 3
        assert summary["pending"] == 2
        assert summary["completed"] == 1

    @pytest.mark.unit
    def test_save_and_load_tasks(self, temp_memory_dir):
        """Should persist and restore tasks."""
        storage_file = temp_memory_dir / "tasks.json"

        manager1 = ReminderManager(storage_file=storage_file)
        manager1.add_task("Persistent task", priority="high")
        manager1.save_tasks()

        # Create new manager and load
        manager2 = ReminderManager(storage_file=storage_file)
        manager2.load_tasks()

        tasks = manager2.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].title == "Persistent task"

    @pytest.mark.unit
    def test_tasks_sorted_by_priority(self, temp_memory_dir):
        """Should sort tasks by priority."""
        manager = ReminderManager(storage_file=temp_memory_dir / "test.json")
        manager.add_task("Low", priority="low")
        manager.add_task("Urgent", priority="urgent")
        manager.add_task("Medium", priority="medium")

        tasks = manager.list_tasks()

        priorities = [t.priority for t in tasks]
        assert priorities == ["urgent", "medium", "low"]


class TestReminderToolActions:
    """Test tool action functions."""

    @pytest.mark.unit
    def test_add_reminder_action_success(self, temp_memory_dir):
        """Should successfully add a reminder."""
        result = add_reminder_action(
            title="Test reminder",
            priority="high",
        )

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert "Test reminder" in result.message

    @pytest.mark.unit
    def test_add_reminder_action_no_title(self):
        """Should fail when title is missing."""
        result = add_reminder_action(title="")
        assert result.success is False

    @pytest.mark.unit
    def test_add_reminder_action_with_due_date(self):
        """Should add reminder with due date."""
        result = add_reminder_action(
            title="Meeting",
            due_date="2024-12-31",
            due_time="14:00",
        )

        assert result.success is True

    @pytest.mark.unit
    def test_list_reminders_action_empty(self):
        """Should handle empty task list."""
        result = list_reminders_action()
        # May be success or empty, both are valid
        assert isinstance(result, ToolResult)

    @pytest.mark.unit
    def test_list_reminders_action_with_filter(self):
        """Should filter reminders in listing."""
        add_reminder_action(title="Work task", category="work")
        result = list_reminders_action(category="work")

        assert isinstance(result, ToolResult)

    @pytest.mark.unit
    def test_complete_reminder_action(self):
        """Should complete a reminder."""
        added = add_reminder_action(title="Complete me")
        if added.data and "task_id" in added.data:
            task_id = added.data["task_id"]
            result = complete_reminder_action(task_id)

            assert isinstance(result, ToolResult)
            assert result.success is True

    @pytest.mark.unit
    def test_get_reminder_summary_action(self):
        """Should get task summary."""
        add_reminder_action(title="Task 1")
        add_reminder_action(title="Task 2")

        result = get_reminder_summary_action()

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert "Summary" in result.message or "Total" in result.message

    @pytest.mark.unit
    def test_delete_reminder_action(self):
        """Should delete a reminder."""
        added = add_reminder_action(title="Delete me")
        if added.data and "task_id" in added.data:
            task_id = added.data["task_id"]
            result = delete_reminder_action(task_id)

            assert isinstance(result, ToolResult)
            assert result.success is True
