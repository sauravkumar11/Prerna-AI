"""
reminder_tool.py
================
Task/Reminder Management Tool for Prerna

Capabilities:
  - Create, list, and complete tasks/reminders
  - Set time-based reminders
  - Organize tasks by priority and category
  - Mark tasks as done
  - Get task summary

Usage examples:
  "Add a reminder to call mom at 3 PM"
  "Show my tasks"
  "Mark the meeting as done"
  "Create a high-priority task to finish the report"

v1.1.1 addition: Comprehensive task management with persistence
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum

from agent.registry import action, ToolResult, safe
from config.settings import DATA_DIR
from utils.logger import get_logger

logger = get_logger(__name__)


class TaskPriority(Enum):
    """Task priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TaskStatus(Enum):
    """Task status values."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """Represents a single task/reminder."""
    id: str
    title: str
    description: Optional[str] = None
    priority: str = TaskPriority.MEDIUM.value
    status: str = TaskStatus.PENDING.value
    category: Optional[str] = None
    due_date: Optional[str] = None  # ISO format: YYYY-MM-DD
    due_time: Optional[str] = None  # HH:MM format
    created_at: str = ""
    completed_at: Optional[str] = None
    reminders: List[str] = None  # List of reminder times (ISO format)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if self.reminders is None:
            self.reminders = []

    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Task:
        """Create task from dictionary."""
        return cls(**data)

    def is_overdue(self) -> bool:
        """Check if task is overdue."""
        if not self.due_date:
            return False
        try:
            due = datetime.fromisoformat(self.due_date)
            return due < datetime.now() and self.status != TaskStatus.COMPLETED.value
        except ValueError:
            return False

    def get_display_text(self) -> str:
        """Get human-readable task text."""
        parts = [f"[{self.priority.upper()}]", self.title]
        if self.due_date:
            parts.append(f"(due: {self.due_date}")
            if self.due_time:
                parts[-1] += f" {self.due_time}"
            parts[-1] += ")"
        if self.status != TaskStatus.PENDING.value:
            parts.append(f"[{self.status}]")
        return " ".join(parts)


class ReminderManager:
    """Manages tasks and reminders with persistence."""

    def __init__(self, storage_file: Optional[Path] = None):
        """Initialize reminder manager."""
        self.storage_file = storage_file or (DATA_DIR / "reminders.json")
        self.tasks: Dict[str, Task] = {}
        self.load_tasks()

    def load_tasks(self) -> None:
        """Load tasks from storage."""
        try:
            if self.storage_file.exists():
                with open(self.storage_file, "r") as f:
                    data = json.load(f)
                    self.tasks = {
                        task_id: Task.from_dict(task_data)
                        for task_id, task_data in data.items()
                    }
                    logger.info(f"Loaded {len(self.tasks)} tasks from storage")
        except Exception as e:
            logger.error(f"Failed to load tasks: {e}")
            self.tasks = {}

    def save_tasks(self) -> None:
        """Save tasks to storage."""
        try:
            self.storage_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_file, "w") as f:
                data = {task_id: task.to_dict() for task_id, task in self.tasks.items()}
                json.dump(data, f, indent=2, default=str)
                logger.info(f"Saved {len(self.tasks)} tasks to storage")
        except Exception as e:
            logger.error(f"Failed to save tasks: {e}")

    def generate_task_id(self) -> str:
        """Generate unique task ID."""
        import uuid
        return str(uuid.uuid4())[:8]

    def add_task(
        self,
        title: str,
        description: Optional[str] = None,
        priority: str = TaskPriority.MEDIUM.value,
        category: Optional[str] = None,
        due_date: Optional[str] = None,
        due_time: Optional[str] = None,
    ) -> Task:
        """Add a new task."""
        task_id = self.generate_task_id()
        task = Task(
            id=task_id,
            title=title,
            description=description,
            priority=priority,
            category=category,
            due_date=due_date,
            due_time=due_time,
        )
        self.tasks[task_id] = task
        self.save_tasks()
        logger.info(f"Added task: {title}")
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        return self.tasks.get(task_id)

    def list_tasks(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> List[Task]:
        """List tasks with optional filters."""
        tasks = list(self.tasks.values())

        if status:
            tasks = [t for t in tasks if t.status == status]
        if category:
            tasks = [t for t in tasks if t.category == category]
        if priority:
            tasks = [t for t in tasks if t.priority == priority]

        # Sort by priority (urgent first) then due date
        priority_order = {
            TaskPriority.URGENT.value: 0,
            TaskPriority.HIGH.value: 1,
            TaskPriority.MEDIUM.value: 2,
            TaskPriority.LOW.value: 3,
        }
        tasks.sort(
            key=lambda t: (
                priority_order.get(t.priority, 999),
                t.due_date or "9999-12-31",
            )
        )
        return tasks

    def complete_task(self, task_id: str) -> Optional[Task]:
        """Mark task as completed."""
        task = self.tasks.get(task_id)
        if task:
            task.status = TaskStatus.COMPLETED.value
            task.completed_at = datetime.now().isoformat()
            self.save_tasks()
            logger.info(f"Completed task: {task.title}")
        return task

    def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        if task_id in self.tasks:
            title = self.tasks[task_id].title
            del self.tasks[task_id]
            self.save_tasks()
            logger.info(f"Deleted task: {title}")
            return True
        return False

    def get_overdue_tasks(self) -> List[Task]:
        """Get all overdue tasks."""
        return [t for t in self.tasks.values() if t.is_overdue()]

    def get_today_tasks(self) -> List[Task]:
        """Get tasks due today."""
        today = datetime.now().date().isoformat()
        return [
            t for t in self.tasks.values()
            if t.due_date == today and t.status != TaskStatus.COMPLETED.value
        ]

    def get_summary(self) -> Dict[str, Any]:
        """Get task summary statistics."""
        tasks = list(self.tasks.values())
        return {
            "total": len(tasks),
            "pending": len([t for t in tasks if t.status == TaskStatus.PENDING.value]),
            "in_progress": len([t for t in tasks if t.status == TaskStatus.IN_PROGRESS.value]),
            "completed": len([t for t in tasks if t.status == TaskStatus.COMPLETED.value]),
            "overdue": len(self.get_overdue_tasks()),
            "today": len(self.get_today_tasks()),
        }


# Global instance
_reminder_manager: Optional[ReminderManager] = None


def get_reminder_manager() -> ReminderManager:
    """Get or create global reminder manager."""
    global _reminder_manager
    if _reminder_manager is None:
        _reminder_manager = ReminderManager()
    return _reminder_manager


# ── Tool Actions ──────────────────────────────────────────────────────────────

@safe
@action("reminder_tool", "add_task", "Create a new task or reminder")
def add_reminder_action(
    title: str,
    description: Optional[str] = None,
    priority: str = "medium",
    category: Optional[str] = None,
    due_date: Optional[str] = None,
    due_time: Optional[str] = None,
) -> ToolResult:
    """
    Add a new task/reminder.

    Args:
        title: Task title (required)
        description: Detailed description
        priority: low|medium|high|urgent
        category: Task category (work, personal, etc.)
        due_date: Due date in YYYY-MM-DD format
        due_time: Due time in HH:MM format

    Examples:
        "Add a task to call mom"
        "Create a high-priority reminder for the meeting at 3 PM"
        "Add: write report, due Friday, high priority"
    """
    if not title or not isinstance(title, str):
        return ToolResult(False, "Task title is required and must be a string")

    try:
        manager = get_reminder_manager()
        task = manager.add_task(
            title=title,
            description=description,
            priority=priority.lower() if priority else "medium",
            category=category,
            due_date=due_date,
            due_time=due_time,
        )
        return ToolResult(
            True,
            f"Task created: {task.title}",
            speech=f"Created task: {title}",
            data={"task_id": task.id, "task": task.to_dict()},
        )
    except Exception as e:
        logger.error(f"Failed to add task: {e}")
        return ToolResult(False, f"Failed to create task: {str(e)}")


@safe
@action("reminder_tool", "list_tasks", "Show all tasks and reminders")
def list_reminders_action(
    status: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
) -> ToolResult:
    """
    List tasks with optional filters.

    Args:
        status: pending|in_progress|completed|cancelled
        category: Filter by category
        priority: low|medium|high|urgent

    Examples:
        "Show my tasks"
        "List high-priority tasks"
        "Show pending work tasks"
    """
    try:
        manager = get_reminder_manager()
        tasks = manager.list_tasks(
            status=status.lower() if status else None,
            category=category.lower() if category else None,
            priority=priority.lower() if priority else None,
        )

        if not tasks:
            return ToolResult(True, "No tasks found", speech="No tasks to show")

        # Format for display
        task_list = "\n".join([f"• {t.get_display_text()}" for t in tasks])
        summary = f"Found {len(tasks)} task(s):\n{task_list}"

        return ToolResult(
            True,
            summary,
            speech=f"Found {len(tasks)} tasks",
            data={"tasks": [t.to_dict() for t in tasks]},
        )
    except Exception as e:
        logger.error(f"Failed to list tasks: {e}")
        return ToolResult(False, f"Failed to list tasks: {str(e)}")


@safe
@action("reminder_tool", "complete_task", "Mark a task as done")
def complete_reminder_action(task_id: str) -> ToolResult:
    """
    Mark a task as completed.

    Args:
        task_id: ID of the task to complete

    Examples:
        "Mark the meeting as done"
        "Complete task 12345"
    """
    if not task_id:
        return ToolResult(False, "Task ID is required")

    try:
        manager = get_reminder_manager()
        task = manager.complete_task(task_id)

        if not task:
            return ToolResult(False, f"Task {task_id} not found")

        return ToolResult(
            True,
            f"Task completed: {task.title}",
            speech=f"Marked {task.title} as done",
            data={"task_id": task_id, "task": task.to_dict()},
        )
    except Exception as e:
        logger.error(f"Failed to complete task: {e}")
        return ToolResult(False, f"Failed to complete task: {str(e)}")


@safe
@action("reminder_tool", "get_summary", "Get task summary and statistics")
def get_reminder_summary_action() -> ToolResult:
    """
    Get a summary of all tasks.

    Examples:
        "Show my task summary"
        "How many tasks do I have?"
    """
    try:
        manager = get_reminder_manager()
        summary = manager.get_summary()

        message = (
            f"Task Summary:\n"
            f"  Total: {summary['total']}\n"
            f"  Pending: {summary['pending']}\n"
            f"  In Progress: {summary['in_progress']}\n"
            f"  Completed: {summary['completed']}\n"
            f"  Overdue: {summary['overdue']}\n"
            f"  Due Today: {summary['today']}"
        )

        speech = f"You have {summary['pending']} pending tasks and {summary['overdue']} overdue"

        return ToolResult(
            True,
            message,
            speech=speech,
            data=summary,
        )
    except Exception as e:
        logger.error(f"Failed to get summary: {e}")
        return ToolResult(False, f"Failed to get summary: {str(e)}")


@safe
@action("reminder_tool", "delete_task", "Delete a task")
def delete_reminder_action(task_id: str) -> ToolResult:
    """
    Delete a task permanently.

    Args:
        task_id: ID of the task to delete

    Examples:
        "Delete task 12345"
        "Remove the meeting reminder"
    """
    if not task_id:
        return ToolResult(False, "Task ID is required")

    try:
        manager = get_reminder_manager()
        success = manager.delete_task(task_id)

        if not success:
            return ToolResult(False, f"Task {task_id} not found")

        return ToolResult(
            True,
            f"Task deleted successfully",
            speech="Task deleted",
            data={"task_id": task_id},
        )
    except Exception as e:
        logger.error(f"Failed to delete task: {e}")
        return ToolResult(False, f"Failed to delete task: {str(e)}")


logger.info("✓ Reminder tool loaded")
