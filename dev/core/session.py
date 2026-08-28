"""
Unified Session and State Management for Dev CLI.

Consolidates interactive session history, background subagent sessions,
checkpoint references, and thread-safe persistence.
"""

from __future__ import annotations

import json
import os
import time
import uuid
import asyncio
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional, Dict, List


@dataclass
class SessionMessage:
    """A single message within an agent session."""
    role: str
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class SessionState:
    """Complete persistent state of an interactive or background session."""
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = "New Session"
    project_path: str = "."
    model: str = "default"
    status: str = "active"  # active, background, completed, paused, failed
    pid: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    stopped_at: float = 0.0
    total_tokens_sent: int = 0
    total_tokens_received: int = 0
    total_cost: float = 0.0
    messages: List[Dict[str, Any]] = field(default_factory=list)
    checkpoints: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    log_file: str = ""
    error: str = ""


class UnifiedSessionManager:
    """
    Centralized session manager for Dev.
    
    Handles:
    1. Interactive conversation persistence & resumption
    2. Background 24/7 worker sessions
    3. Session pruning & atomic disk persistence
    """
    
    MAX_SAVED_SESSIONS = 100

    def __init__(self, base_dir: str = ".dev"):
        self.base_dir = os.path.abspath(base_dir)
        self.sessions_dir = os.path.join(self.base_dir, "sessions")
        self.history_dir = os.path.join(self.base_dir, "history")
        os.makedirs(self.sessions_dir, exist_ok=True)
        os.makedirs(self.history_dir, exist_ok=True)
        self._index_file = os.path.join(self.sessions_dir, "index.json")
        self._sessions: Dict[str, SessionState] = {}
        self._load_index()

    def _load_index(self) -> None:
        """Load session index from disk."""
        if os.path.isfile(self._index_file):
            try:
                with open(self._index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for sid, sdata in data.items():
                    self._sessions[sid] = SessionState(**sdata)
            except Exception:
                self._sessions = {}

    def _save_index(self) -> None:
        """Atomically persist session index."""
        temp_file = self._index_file + f".tmp.{os.getpid()}"
        data = {sid: asdict(s) for sid, s in self._sessions.items()}
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            if os.path.exists(self._index_file):
                os.replace(temp_file, self._index_file)
            else:
                os.rename(temp_file, self._index_file)
        except Exception:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    pass

    def create_session(
        self,
        title: str = "New Session",
        project_path: str = ".",
        model: str = "default",
        is_background: bool = False
    ) -> SessionState:
        """Create and register a new session."""
        session = SessionState(
            title=title,
            project_path=os.path.abspath(project_path),
            model=model,
            status="background" if is_background else "active",
        )
        if is_background:
            session.log_file = os.path.join(self.sessions_dir, f"{session.session_id}.log")

        self._sessions[session.session_id] = session
        self._cleanup_old_sessions()
        self._save_index()
        self.save_session_detail(session)
        return session

    def get_session(self, session_id: str) -> Optional[SessionState]:
        """Get a session by ID, loading full message history if needed."""
        session = self._sessions.get(session_id)
        if session:
            detail_file = os.path.join(self.history_dir, f"{session_id}.json")
            if os.path.isfile(detail_file):
                try:
                    with open(detail_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    session.messages = data.get("messages", [])
                except Exception:
                    pass  # Intentional: non-critical: best-effort operation
        return session

    def list_sessions(self, limit: int = 20) -> List[SessionState]:
        """List active and recent sessions sorted by updated_at descending."""
        sorted_sessions = sorted(
            self._sessions.values(),
            key=lambda s: s.updated_at,
            reverse=True
        )
        return sorted_sessions[:limit]

    def save_session_detail(self, session: SessionState) -> None:
        """Save full session conversation history to disk."""
        session.updated_at = time.time()
        self._sessions[session.session_id] = session
        self._save_index()

        detail_file = os.path.join(self.history_dir, f"{session.session_id}.json")
        temp_file = detail_file + f".tmp.{os.getpid()}"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(asdict(session), f, indent=2)
            if os.path.exists(detail_file):
                os.replace(temp_file, detail_file)
            else:
                os.rename(temp_file, detail_file)
        except Exception:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    pass

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and its persistent files."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            self._save_index()

            detail_file = os.path.join(self.history_dir, f"{session_id}.json")
            if os.path.exists(detail_file):
                try:
                    os.remove(detail_file)
                except OSError:
                    pass
            return True
        return False

    def _cleanup_old_sessions(self) -> None:
        """Retain within MAX_SAVED_SESSIONS by evicting oldest completed sessions."""
        if len(self._sessions) <= self.MAX_SAVED_SESSIONS:
            return

        sorted_sessions = sorted(
            self._sessions.items(),
            key=lambda item: item[1].updated_at
        )

        excess = len(self._sessions) - self.MAX_SAVED_SESSIONS
        for sid, sess in sorted_sessions:
            if excess <= 0:
                break
            if sess.status in ("completed", "failed", "stopped"):
                self.delete_session(sid)
                excess -= 1
