"""
24/7 Task Queue for Dev.

Adapted from OpenHands' automation patterns:
- Persistent task queue (SQLite-backed)
- Background worker with rate limiting
- Auto-retry with exponential backoff
- Task status tracking
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Callable

from pydantic import BaseModel


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class TaskPriority(int, Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


class Task(BaseModel):
    """A task in the queue."""
    id: str = ""
    prompt: str
    agent_id: str = "coder"
    project_path: str = "."
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    
    created_at: float = 0
    started_at: float | None = None
    completed_at: float | None = None
    
    result: dict | None = None
    error: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    
    def __init__(self, **data):
        if not data.get("id"):
            data["id"] = str(uuid.uuid4())
        if not data.get("created_at"):
            data["created_at"] = time.time()
        super().__init__(**data)


class TaskQueue:
    """
    Persistent task queue backed by SQLite.
    
    Supports:
    - Priority ordering
    - Persistent storage (survives restarts)
    - Auto-retry with exponential backoff
    - Task status tracking
    - 24/7 background processing
    """
    
    def __init__(self, db_path: str = ".dev/tasks.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._workers: list[asyncio.Task] = []
        self._running = False
        self._handlers: dict[str, Callable] = {}
    
    def _init_db(self):
        """Initialize SQLite database."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                prompt TEXT NOT NULL,
                agent_id TEXT DEFAULT 'coder',
                project_path TEXT DEFAULT '.',
                status TEXT DEFAULT 'pending',
                priority INTEGER DEFAULT 1,
                created_at REAL NOT NULL,
                started_at REAL,
                completed_at REAL,
                result TEXT,
                error TEXT,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority DESC, created_at ASC)
        """)
        conn.commit()
        conn.close()
    
    def add_task(self, task: Task) -> str:
        """Add a task to the queue."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            """INSERT INTO tasks 
               (id, prompt, agent_id, project_path, status, priority, created_at, retry_count, max_retries)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task.id, task.prompt, task.agent_id, task.project_path,
                task.status.value, task.priority.value, task.created_at,
                task.retry_count, task.max_retries,
            ),
        )
        conn.commit()
        conn.close()
        return task.id
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        conn.close()
        
        if not row:
            return None
        
        return Task(
            id=row["id"],
            prompt=row["prompt"],
            agent_id=row["agent_id"],
            project_path=row["project_path"],
            status=TaskStatus(row["status"]),
            priority=TaskPriority(row["priority"]),
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            result=json.loads(row["result"]) if row["result"] else None,
            error=row["error"],
            retry_count=row["retry_count"],
            max_retries=row["max_retries"],
        )
    
    def get_next_task(self) -> Optional[Task]:
        """Get the next pending task ordered by priority."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT * FROM tasks 
               WHERE status IN ('pending', 'retrying')
               ORDER BY priority DESC, created_at ASC
               LIMIT 1"""
        ).fetchone()
        conn.close()
        
        if not row:
            return None
        
        return Task(
            id=row["id"],
            prompt=row["prompt"],
            agent_id=row["agent_id"],
            project_path=row["project_path"],
            status=TaskStatus(row["status"]),
            priority=TaskPriority(row["priority"]),
            created_at=row["created_at"],
            retry_count=row["retry_count"],
            max_retries=row["max_retries"],
        )
    
    def update_task(self, task: Task):
        """Update a task in the database."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            """UPDATE tasks SET
               status = ?, started_at = ?, completed_at = ?,
               result = ?, error = ?, retry_count = ?
               WHERE id = ?""",
            (
                task.status.value,
                task.started_at,
                task.completed_at,
                json.dumps(task.result) if task.result else None,
                task.error,
                task.retry_count,
                task.id,
            ),
        )
        conn.commit()
        conn.close()
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending task."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute(
            "UPDATE tasks SET status = 'cancelled' WHERE id = ? AND status = 'pending'",
            (task_id,),
        )
        conn.commit()
        conn.close()
        return cursor.rowcount > 0
    
    def list_tasks(self, status: Optional[str] = None, limit: int = 50) -> list[Task]:
        """List tasks, optionally filtered by status."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        
        if status:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        
        conn.close()
        
        return [
            Task(
                id=r["id"], prompt=r["prompt"], agent_id=r["agent_id"],
                project_path=r["project_path"], status=TaskStatus(r["status"]),
                priority=TaskPriority(r["priority"]), created_at=r["created_at"],
                started_at=r["started_at"], completed_at=r["completed_at"],
                result=json.loads(r["result"]) if r["result"] else None,
                error=r["error"], retry_count=r["retry_count"],
                max_retries=r["max_retries"],
            )
            for r in rows
        ]
    
    def register_handler(self, agent_id: str, handler: Callable):
        """Register a handler function for an agent type."""
        self._handlers[agent_id] = handler
    
    async def start_worker(self, poll_interval: float = 2.0):
        """Start the background worker that processes tasks."""
        self._running = True
        
        while self._running:
            task = self.get_next_task()
            
            if not task:
                await asyncio.sleep(poll_interval)
                continue
            
            # Mark as running
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()
            self.update_task(task)
            
            # Find handler
            handler = self._handlers.get(task.agent_id)
            if not handler:
                task.status = TaskStatus.FAILED
                task.error = f"No handler registered for agent: {task.agent_id}"
                task.completed_at = time.time()
                self.update_task(task)
                continue
            
            try:
                result = await handler(task)
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.completed_at = time.time()
            except Exception as e:
                task.retry_count += 1
                if task.retry_count >= task.max_retries:
                    task.status = TaskStatus.FAILED
                    task.error = str(e)
                    task.completed_at = time.time()
                else:
                    task.status = TaskStatus.RETRYING
                    # Exponential backoff
                    await asyncio.sleep(2 ** task.retry_count)
            
            self.update_task(task)
    
    def stop_worker(self):
        """Stop the background worker."""
        self._running = False
    
    def get_stats(self) -> dict:
        """Get queue statistics."""
        conn = sqlite3.connect(str(self.db_path))
        stats = {}
        
        for status in TaskStatus:
            count = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE status = ?", (status.value,)
            ).fetchone()[0]
            stats[status.value] = count
        
        conn.close()
        return stats
