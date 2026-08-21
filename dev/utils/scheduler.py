"""
Scheduled agents with cron-like scheduling.

Like Cline's scheduled agents:
- Run agents on cron schedules
- Daily PR summaries, weekly dependency checks
- Schedules persist across restarts
"""
from __future__ import annotations
import os
import json
import time
import threading
from dataclasses import dataclass, field
from typing import Optional, Callable, Any
from datetime import datetime, timedelta
from enum import Enum


class ScheduleStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ScheduledTask:
    """A scheduled agent task."""
    id: str
    name: str
    prompt: str
    cron_expression: str  # Simple cron: "0 9 * * MON-FRI" or interval: "every 1h"
    status: ScheduleStatus = ScheduleStatus.ACTIVE
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    run_count: int = 0
    last_result: Optional[str] = None
    workspace: str = "."
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class SimpleCron:
    """Simple cron parser for scheduling."""
    
    @staticmethod
    def parse_interval(expression: str) -> Optional[int]:
        """Parse interval expression like 'every 1h', 'every 30m', 'every 1d'. Returns seconds."""
        if not expression.startswith("every "):
            return None
        
        parts = expression[6:].strip()
        try:
            if parts.endswith("s"):
                return int(parts[:-1])
            elif parts.endswith("m"):
                return int(parts[:-1]) * 60
            elif parts.endswith("h"):
                return int(parts[:-1]) * 3600
            elif parts.endswith("d"):
                return int(parts[:-1]) * 86400
        except ValueError:
            pass
        return None

    @staticmethod
    def should_run(task: ScheduledTask) -> bool:
        """Check if a task should run based on its schedule."""
        if task.status != ScheduleStatus.ACTIVE:
            return False
        
        interval = SimpleCron.parse_interval(task.cron_expression)
        if interval:
            if task.last_run:
                last = datetime.fromisoformat(task.last_run)
                if datetime.now() - last >= timedelta(seconds=interval):
                    return True
            else:
                return True
            return False
        
        # Simple day-of-week cron: "0 9 * * MON-FRI"
        try:
            parts = task.cron_expression.split()
            if len(parts) == 5:
                hour = int(parts[1]) if parts[1] != "*" else None
                dow = parts[4]  # Day of week
                
                now = datetime.now()
                if hour is not None and now.hour != hour:
                    return False
                
                if dow != "*":
                    days = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}
                    allowed = set()
                    for d in dow.split(","):
                        if "-" in d:
                            start, end = d.split("-")
                            for i in range(days.get(start, 0), days.get(end, 0) + 1):
                                allowed.add(i)
                        else:
                            allowed.add(days.get(d, -1))
                    
                    if now.weekday() not in allowed:
                        return False
                
                # Check if already ran today
                if task.last_run:
                    last = datetime.fromisoformat(task.last_run)
                    if last.date() == now.date():
                        return False
                
                return True
        except (ValueError, KeyError):
            pass
        
        return False


class AgentScheduler:
    """Manages scheduled agent tasks."""
    
    def __init__(self, project_root: str = "."):
        self.project_root = os.path.abspath(project_root)
        self.tasks: dict[str, ScheduledTask] = {}
        self._schedule_dir = os.path.join(self.project_root, ".dev", "schedules")
        os.makedirs(self._schedule_dir, exist_ok=True)
        self._runner_thread: Optional[threading.Thread] = None
        self._running = False
        self._on_run: Optional[Callable] = None
        self._load_tasks()

    def _load_tasks(self):
        """Load tasks from disk."""
        index_path = os.path.join(self._schedule_dir, "index.json")
        if os.path.exists(index_path):
            with open(index_path) as f:
                data = json.load(f)
            for task_data in data.get("tasks", []):
                task = ScheduledTask(
                    id=task_data["id"],
                    name=task_data["name"],
                    prompt=task_data["prompt"],
                    cron_expression=task_data["cron_expression"],
                    status=ScheduleStatus(task_data.get("status", "active")),
                    last_run=task_data.get("last_run"),
                    next_run=task_data.get("next_run"),
                    run_count=task_data.get("run_count", 0),
                    last_result=task_data.get("last_result"),
                    workspace=task_data.get("workspace", "."),
                )
                self.tasks[task.id] = task

    def _save_tasks(self):
        """Save tasks to disk."""
        index_path = os.path.join(self._schedule_dir, "index.json")
        data = {
            "tasks": [
                {
                    "id": t.id,
                    "name": t.name,
                    "prompt": t.prompt,
                    "cron_expression": t.cron_expression,
                    "status": t.status.value,
                    "last_run": t.last_run,
                    "next_run": t.next_run,
                    "run_count": t.run_count,
                    "last_result": t.last_result,
                    "workspace": t.workspace,
                }
                for t in self.tasks.values()
            ]
        }
        with open(index_path, "w") as f:
            json.dump(data, f, indent=2)

    def create_task(self, name: str, prompt: str, cron: str, workspace: str = ".") -> ScheduledTask:
        """Create a new scheduled task."""
        task_id = f"task-{len(self.tasks)}"
        task = ScheduledTask(
            id=task_id,
            name=name,
            prompt=prompt,
            cron_expression=cron,
            workspace=workspace,
        )
        self.tasks[task_id] = task
        self._save_tasks()
        return task

    def pause_task(self, task_id: str) -> bool:
        """Pause a scheduled task."""
        if task_id in self.tasks:
            self.tasks[task_id].status = ScheduleStatus.PAUSED
            self._save_tasks()
            return True
        return False

    def resume_task(self, task_id: str) -> bool:
        """Resume a paused task."""
        if task_id in self.tasks:
            self.tasks[task_id].status = ScheduleStatus.ACTIVE
            self._save_tasks()
            return True
        return False

    def delete_task(self, task_id: str) -> bool:
        """Delete a scheduled task."""
        if task_id in self.tasks:
            del self.tasks[task_id]
            self._save_tasks()
            return True
        return False

    def record_run(self, task_id: str, result: str = ""):
        """Record that a task ran."""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.last_run = datetime.now().isoformat()
            task.run_count += 1
            task.last_result = result[:500]
            self._save_tasks()

    def get_due_tasks(self) -> list[ScheduledTask]:
        """Get all tasks that are due to run."""
        due = []
        for task in self.tasks.values():
            if SimpleCron.should_run(task):
                due.append(task)
        return due

    def list_tasks(self) -> list[dict]:
        """List all scheduled tasks."""
        return [
            {
                "id": t.id,
                "name": t.name,
                "cron": t.cron_expression,
                "status": t.status.value,
                "last_run": t.last_run,
                "run_count": t.run_count,
            }
            for t in self.tasks.values()
        ]

    def start(self, on_run: Callable = None):
        """Start the scheduler loop in background."""
        self._on_run = on_run
        self._running = True
        self._runner_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._runner_thread.start()

    def stop(self):
        """Stop the scheduler loop."""
        self._running = False
        if self._runner_thread:
            self._runner_thread.join(timeout=5)

    def _run_loop(self):
        """Background loop that checks for due tasks."""
        while self._running:
            due_tasks = self.get_due_tasks()
            for task in due_tasks:
                if self._on_run:
                    try:
                        result = self._on_run(task)
                        self.record_run(task.id, str(result))
                    except Exception as e:
                        self.record_run(task.id, f"ERROR: {e}")
            time.sleep(60)  # Check every minute
