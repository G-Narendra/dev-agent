"""
File Watcher for Dev.

Watches file changes and provides agent mailbox + plan approval.
"""

from __future__ import annotations

import os
import time
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional
from pathlib import Path
from enum import Enum


class FileChange:
    """A detected file change."""
    def __init__(self, path: str, change_type: str, size: int = 0):
        self.path = path
        self.change_type = change_type  # "created", "modified", "deleted"
        self.size = size
        self.timestamp = time.time()
    
    @property
    def size(self) -> int:
        return self._size
    
    @size.setter
    def size(self, value: int):
        self._size = value


class FileWatcher:
    """Watches a directory for file changes."""
    
    def __init__(self, watch_dir: str = ".", interval: float = 2.0):
        self.watch_dir = os.path.abspath(watch_dir)
        self.interval = interval
        self._callbacks: list[Callable] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._file_mtimes: dict[str, float] = {}
    
    def add_callback(self, callback: Callable):
        """Add a callback for file changes."""
        self._callbacks.append(callback)
    
    def start(self):
        """Start watching in background thread."""
        if self._running:
            return
        
        # Snapshot current file states
        self._file_mtimes = self._scan_files()
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop watching."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
    
    def _scan_files(self) -> dict[str, float]:
        """Scan directory for file modification times."""
        mtimes = {}
        for root, dirs, files in os.walk(self.watch_dir):
            # Skip hidden dirs and __pycache__
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for f in files:
                if f.startswith("."):
                    continue
                fpath = os.path.join(root, f)
                try:
                    mtimes[fpath] = os.path.getmtime(fpath)
                except OSError:
                    pass
        return mtimes
    
    def _watch_loop(self):
        """Background watch loop."""
        while self._running:
            time.sleep(self.interval)
            new_mtimes = self._scan_files()
            
            # Detect changes
            for fpath, mtime in new_mtimes.items():
                old_mtime = self._file_mtimes.get(fpath)
                if old_mtime is None:
                    change = FileChange(fpath, "created", os.path.getsize(fpath))
                elif mtime > old_mtime:
                    change = FileChange(fpath, "modified", os.path.getsize(fpath))
                else:
                    continue
                
                for cb in self._callbacks:
                    try:
                        cb(change)
                    except Exception:
                        pass
            
            # Detect deletions
            for fpath in self._file_mtimes:
                if fpath not in new_mtimes:
                    change = FileChange(fpath, "deleted")
                    for cb in self._callbacks:
                        try:
                            cb(change)
                        except Exception:
                            pass
            
            self._file_mtimes = new_mtimes


@dataclass
class MailMessage:
    """A message in the agent mailbox."""
    sender: str = ""
    recipient: str = ""
    content: str = ""
    timestamp: float = field(default_factory=time.time)
    is_read: bool = False
    
    def mark_read(self) -> str:
        """Mark as read and return content."""
        self.is_read = True
        return self.content


class AgentMailbox:
    """Inter-agent communication mailbox."""
    
    def __init__(self):
        self._mailboxes: dict[str, list[MailMessage]] = {}
    
    def send(self, sender: str, recipient: str, content: str):
        """Send a message to an agent."""
        if recipient not in self._mailboxes:
            self._mailboxes[recipient] = []
        self._mailboxes[recipient].append(
            MailMessage(sender=sender, recipient=recipient, content=content)
        )
    
    def receive(self, agent_id: str) -> list[MailMessage]:
        """Get unread messages for an agent."""
        messages = self._mailboxes.get(agent_id, [])
        unread = [m for m in messages if not m.is_read]
        return unread
    
    def broadcast(self, sender: str, content: str):
        """Broadcast a message to all agents."""
        for agent_id in self._mailboxes:
            if agent_id != sender:
                self.send(sender, agent_id, content)
    
    def mark_read(self, agent_id: str):
        """Mark all messages as read for an agent."""
        for msg in self._mailboxes.get(agent_id, []):
            msg.is_read = True
    
    def clear(self, agent_id: str):
        """Clear all messages for an agent."""
        self._mailboxes.pop(agent_id, None)
    
    def get_mailbox_status(self) -> dict:
        """Get status of all mailboxes."""
        return {
            agent_id: {
                "total": len(msgs),
                "unread": sum(1 for m in msgs if not m.is_read),
            }
            for agent_id, msgs in self._mailboxes.items()
        }


@dataclass
class PlanStep:
    """A step in an execution plan."""
    description: str
    agent_id: str = ""
    status: str = "pending"  # pending, in_progress, completed, failed
    estimated_tokens: int = 0


@dataclass
class Plan:
    """An execution plan for multi-agent tasks."""
    name: str
    steps: list[PlanStep] = field(default_factory=list)
    status: str = "draft"  # draft, submitted, approved, executing, completed
    created_at: float = field(default_factory=time.time)
    approved_at: Optional[float] = None
    approved_by: Optional[str] = None


class PlanApproval:
    """Manages plan approval workflow."""
    
    def __init__(self):
        self._plans: dict[str, Plan] = {}
        self._pending: list[str] = []
    
    def create_plan(self, name: str, steps: list[dict]) -> Plan:
        """Create a new plan."""
        plan_steps = [PlanStep(**s) for s in steps]
        plan = Plan(name=name, steps=plan_steps)
        self._plans[name] = plan
        return plan
    
    def submit_for_approval(self, name: str):
        """Submit a plan for approval."""
        if name in self._plans:
            self._plans[name].status = "submitted"
            self._pending.append(name)
    
    def approve(self, name: str, approver: str = "user"):
        """Approve a plan."""
        if name in self._plans:
            self._plans[name].status = "approved"
            self._plans[name].approved_at = time.time()
            self._plans[name].approved_by = approver
            if name in self._pending:
                self._pending.remove(name)
    
    def reject(self, name: str):
        """Reject a plan."""
        if name in self._plans:
            self._plans[name].status = "rejected"
            if name in self._pending:
                self._pending.remove(name)
    
    def start_execution(self, name: str):
        """Mark plan as executing."""
        if name in self._plans:
            self._plans[name].status = "executing"
    
    def complete_step(self, plan_name: str, step_index: int):
        """Mark a step as completed."""
        if plan_name in self._plans:
            steps = self._plans[plan_name].steps
            if 0 <= step_index < len(steps):
                steps[step_index].status = "completed"
    
    def get_plan(self, name: str) -> Optional[Plan]:
        """Get a plan by name."""
        return self._plans.get(name)
    
    def get_pending(self) -> list[Plan]:
        """Get plans pending approval."""
        return [self._plans[n] for n in self._pending if n in self._plans]
    
    def format_plan(self, plan: Plan) -> str:
        """Format a plan for display."""
        lines = [f"Plan: {plan.name} ({plan.status})"]
        for i, step in enumerate(plan.steps):
            status_icon = {"pending": "○", "in_progress": "◐", "completed": "●", "failed": "✗"}.get(step.status, "?")
            lines.append(f"  {status_icon} {i+1}. {step.description} [{step.agent_id}]")
        return "\n".join(lines)
