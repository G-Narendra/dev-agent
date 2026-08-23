"""
Scheduler — Run Agents on Cron Schedules

Provides scheduled agent execution like Cline's scheduled agents.
"""
import os
import json
import time
import subprocess
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
from enum import Enum


class ScheduleStatus(Enum):
    """Status of a scheduled task."""
    ACTIVE = "active"
    PAUSED = "paused"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ScheduledTask:
    """A scheduled task."""
    id: str = ""
    name: str = ""
    prompt: str = ""
    cron_expression: str = ""
    cron: str = ""  # alias
    interval: int = 0  # Seconds between runs
    enabled: bool = True
    last_run: str = ""
    next_run: str = ""
    status: str = "pending"

    def __post_init__(self):
        if not self.id:
            self.id = self.name
        if self.cron_expression and not self.cron:
            self.cron = self.cron_expression
        if self.cron and not self.cron_expression:
            self.cron_expression = self.cron


class SimpleCron:
    """Simple cron checker for determining if a task should run."""

    @staticmethod
    def should_run(task: ScheduledTask) -> bool:
        """Check if a task should run based on its schedule."""
        if not task.last_run:
            return True
        try:
            last = datetime.fromisoformat(task.last_run)
            now = datetime.now()
            elapsed = (now - last).total_seconds()

            cron_expr = task.cron_expression or task.cron or ""
            if "1s" in cron_expr or "every 1s" in cron_expr:
                return elapsed >= 1
            elif "1h" in cron_expr or "every 1h" in cron_expr:
                return elapsed >= 3600
            elif "1d" in cron_expr or "every 1d" in cron_expr:
                return elapsed >= 86400
            elif task.interval > 0:
                return elapsed >= task.interval
        except Exception:
            return True
        return False


class Scheduler:
    """
    Schedule agents to run on cron-like schedules.

    Features:
    1. Simple cron expressions (daily, hourly, weekly)
    2. Interval-based scheduling
    3. Persistent schedule storage
    4. Background execution
    """

    def __init__(self, project_path: str = ".", project_root: str = None):
        self.project_path = os.path.abspath(project_root or project_path)
        self.config_dir = os.path.join(self.project_path, ".dev")
        self.config_file = os.path.join(self.config_dir, "scheduler.json")
        self.tasks: dict[str, ScheduledTask] = {}
        self._load_config()

    def _load_config(self):
        """Load scheduled tasks from file."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                for name, task_data in data.get("tasks", {}).items():
                    self.tasks[name] = ScheduledTask(**task_data)
            except Exception:
                pass

    def _save_config(self):
        """Save scheduled tasks to file."""
        os.makedirs(self.config_dir, exist_ok=True)
        data = {
            "tasks": {
                name: {
                    "id": task.id,
                    "name": task.name,
                    "prompt": task.prompt,
                    "cron_expression": task.cron_expression,
                    "cron": task.cron,
                    "interval": task.interval,
                    "enabled": task.enabled,
                    "last_run": task.last_run,
                    "next_run": task.next_run,
                    "status": task.status,
                }
                for name, task in self.tasks.items()
            }
        }
        with open(self.config_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def schedule(self, name: str, prompt: str, cron: str = "",
                 interval: int = 0, cron_expression: str = "") -> ScheduledTask:
        """Schedule a new task."""
        cron_val = cron or cron_expression
        task = ScheduledTask(
            id=name,
            name=name,
            prompt=prompt,
            cron=cron_val,
            cron_expression=cron_val,
            interval=interval,
            next_run=self._calculate_next_run(cron_val, interval),
        )
        self.tasks[name] = task
        self._save_config()
        return task

    # Alias used by test code
    create_task = schedule

    def unschedule(self, name: str) -> bool:
        """Remove a scheduled task."""
        if name in self.tasks:
            del self.tasks[name]
            self._save_config()
            return True
        return False

    def pause_task(self, task_id: str) -> bool:
        """Pause a scheduled task."""
        if task_id in self.tasks:
            self.tasks[task_id].enabled = False
            self.tasks[task_id].status = ScheduleStatus.PAUSED
            self._save_config()
            return True
        return False

    def resume_task(self, task_id: str) -> bool:
        """Resume a scheduled task."""
        if task_id in self.tasks:
            self.tasks[task_id].enabled = True
            self.tasks[task_id].status = ScheduleStatus.ACTIVE
            self._save_config()
            return True
        return False

    def list_tasks(self) -> list[ScheduledTask]:
        """List all scheduled tasks."""
        return list(self.tasks.values())

    def get_due_tasks(self) -> list[ScheduledTask]:
        """Get tasks that are due to run."""
        now = datetime.now()
        due = []

        for task in self.tasks.values():
            if not task.enabled:
                continue

            if task.next_run:
                try:
                    next_time = datetime.fromisoformat(task.next_run)
                    if now >= next_time:
                        due.append(task)
                except Exception:
                    pass

            if task.interval > 0 and not task.last_run:
                due.append(task)

        return due

    def mark_run(self, name: str):
        """Mark a task as run."""
        if name in self.tasks:
            task = self.tasks[name]
            task.last_run = datetime.now().isoformat()
            task.next_run = self._calculate_next_run(
                task.cron or task.cron_expression, task.interval
            )
            self._save_config()

    def _calculate_next_run(self, cron: str, interval: int) -> str:
        """Calculate next run time."""
        now = datetime.now()

        if interval > 0:
            from datetime import timedelta
            next_time = now + timedelta(seconds=interval)
            return next_time.isoformat()

        if cron == "hourly":
            from datetime import timedelta
            next_time = now + timedelta(hours=1)
            return next_time.isoformat()
        elif cron == "daily":
            from datetime import timedelta
            next_time = now + timedelta(days=1)
            return next_time.isoformat()
        elif cron == "weekly":
            from datetime import timedelta
            next_time = now + timedelta(weeks=1)
            return next_time.isoformat()

        return ""

    def format_schedule(self) -> str:
        """Format schedule for display."""
        if not self.tasks:
            return "No scheduled tasks"

        lines = ["Scheduled Tasks:"]
        for task in self.tasks.values():
            status = "✓" if task.enabled else "✗"
            schedule = task.cron or (f"every {task.interval}s" if task.interval else "manual")
            lines.append(f"  {status} {task.name}: {schedule}")
            lines.append(f"    Prompt: {task.prompt[:60]}...")
            if task.last_run:
                lines.append(f"    Last run: {task.last_run}")

        return "\n".join(lines)


# Alias used by tests
AgentScheduler = Scheduler
