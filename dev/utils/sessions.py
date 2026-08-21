"""
Background session management.

Like Claude Code:
- dev bg <prompt> — start background session
- dev attach <id> — attach to background session
- dev stop <id> — stop background session
- dev logs <id> — show session logs
- dev resume <id> — resume specific session by ID
- dev fork — copy session to background
"""
from __future__ import annotations
import os
import json
import uuid
import time
import subprocess
import signal
from dataclasses import dataclass, field
from typing import Optional, Any
from datetime import datetime
from enum import Enum


class SessionStatus(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"
    ATTACHED = "attached"


@dataclass
class Session:
    """A background agent session."""
    id: str
    prompt: str
    status: SessionStatus = SessionStatus.RUNNING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    stopped_at: Optional[str] = None
    project_path: str = "."
    model: Optional[str] = None
    output_file: Optional[str] = None
    pid: Optional[int] = None
    messages: list = field(default_factory=list)
    files_changed: list = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "prompt": self.prompt[:200],
            "status": self.status.value,
            "created_at": self.created_at,
            "project_path": self.project_path,
            "pid": self.pid,
            "messages": len(self.messages),
            "files_changed": self.files_changed,
        }


class SessionManager:
    """Manages background agent sessions."""
    
    def __init__(self, project_root: str = "."):
        self.project_root = os.path.abspath(project_root)
        self.sessions_dir = os.path.join(self.project_root, ".dev", "sessions")
        self.logs_dir = os.path.join(self.project_root, ".dev", "sessions", "logs")
        os.makedirs(self.sessions_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)
        self.sessions: dict[str, Session] = {}
        self._load_sessions()

    def _load_sessions(self):
        """Load session index from disk."""
        index_path = os.path.join(self.sessions_dir, "index.json")
        if os.path.exists(index_path):
            with open(index_path) as f:
                data = json.load(f)
            for s_data in data.get("sessions", []):
                session = Session(
                    id=s_data["id"],
                    prompt=s_data.get("prompt", ""),
                    status=SessionStatus(s_data.get("status", "stopped")),
                    created_at=s_data.get("created_at", ""),
                    project_path=s_data.get("project_path", "."),
                    pid=s_data.get("pid"),
                    files_changed=s_data.get("files_changed", []),
                )
                self.sessions[session.id] = session

    def _save_sessions(self):
        """Save session index."""
        index_path = os.path.join(self.sessions_dir, "index.json")
        data = {
            "sessions": [s.to_dict() for s in self.sessions.values()]
        }
        with open(index_path, "w") as f:
            json.dump(data, f, indent=2)

    def create_session(self, prompt: str, model: Optional[str] = None) -> Session:
        """Create a new background session."""
        session_id = str(uuid.uuid4())[:8]
        session = Session(
            id=session_id,
            prompt=prompt,
            model=model,
            project_path=self.project_root,
        )
        self.sessions[session_id] = session
        self._save_sessions()
        return session

    def start_session(self, session_id: str) -> bool:
        """Start a background session (launches dev in subprocess)."""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        log_file = os.path.join(self.logs_dir, f"{session_id}.log")
        session.output_file = log_file
        
        try:
            # Launch dev as background process
            proc = subprocess.Popen(
                ["dev", "run", session.prompt],
                cwd=session.project_path,
                stdout=open(log_file, "w"),
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
            session.pid = proc.pid
            session.status = SessionStatus.RUNNING
            session.started_at = datetime.now().isoformat()
            self._save_sessions()
            return True
        except Exception as e:
            session.status = SessionStatus.FAILED
            session.error = str(e)
            self._save_sessions()
            return False

    def stop_session(self, session_id: str) -> bool:
        """Stop a running session."""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        if session.pid:
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/F", "/PID", str(session.pid)], 
                                 capture_output=True)
                else:
                    os.kill(session.pid, signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
        
        session.status = SessionStatus.STOPPED
        session.stopped_at = datetime.now().isoformat()
        session.pid = None
        self._save_sessions()
        return True

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID (supports prefix matching)."""
        # Exact match first
        if session_id in self.sessions:
            return self.sessions[session_id]
        # Prefix match
        for sid, session in self.sessions.items():
            if sid.startswith(session_id):
                return session
        return None

    def get_logs(self, session_id: str, lines: int = 50) -> str:
        """Get recent logs from a session."""
        session = self.sessions.get(session_id)
        if not session or not session.output_file:
            return "No logs available"
        
        if not os.path.exists(session.output_file):
            return "Log file not found"
        
        try:
            with open(session.output_file, encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            return "".join(all_lines[-lines:])
        except Exception as e:
            return f"Error reading logs: {e}"

    def list_sessions(self, include_stopped: bool = False) -> list[dict]:
        """List all sessions."""
        result = []
        for s in self.sessions.values():
            if not include_stopped and s.status == SessionStatus.STOPPED:
                continue
            result.append(s.to_dict())
        return sorted(result, key=lambda x: x["created_at"], reverse=True)

    def resume_session(self, session_id: str) -> Optional[Session]:
        """Resume a stopped session (create new with same prompt)."""
        old = self.get_session(session_id)
        if not old:
            return None
        
        new_session = self.create_session(
            prompt=old.prompt,
            model=old.model,
        )
        new_session.project_path = old.project_path
        self._save_sessions()
        return new_session

    def fork_session(self, session_id: str) -> Optional[Session]:
        """Fork a session to background (copy to new bg session)."""
        old = self.get_session(session_id)
        if not old:
            return None
        
        new_session = self.create_session(
            prompt=old.prompt,
            model=old.model,
        )
        new_session.project_path = old.project_path
        new_session.messages = old.messages.copy()
        self._save_sessions()
        return new_session

    def cleanup_stopped(self, max_age_hours: int = 24):
        """Clean up old stopped sessions."""
        now = datetime.now()
        to_remove = []
        for sid, session in self.sessions.items():
            if session.status in (SessionStatus.STOPPED, SessionStatus.COMPLETED):
                if session.stopped_at:
                    try:
                        stopped = datetime.fromisoformat(session.stopped_at)
                        if (now - stopped).total_seconds() > max_age_hours * 3600:
                            to_remove.append(sid)
                    except ValueError:
                        pass
        
        for sid in to_remove:
            del self.sessions[sid]
            log_file = os.path.join(self.logs_dir, f"{sid}.log")
            if os.path.exists(log_file):
                os.remove(log_file)
        
        if to_remove:
            self._save_sessions()
