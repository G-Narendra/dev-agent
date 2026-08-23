"""
Background Session Manager for Dev.

Manages background agent sessions (start, stop, respawn, logs, remove).
Like Claude Code's background session system.
"""

from __future__ import annotations

import json
import os
import time
import subprocess
import signal
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class BackgroundSession:
    """A background agent session."""
    id: str
    prompt: str
    status: str = "running"  # running, stopped, completed, failed
    pid: int = 0
    project_path: str = "."
    model: str = "default"
    created_at: float = field(default_factory=time.time)
    stopped_at: float = 0.0
    log_file: str = ""
    error: str = ""


class SessionManager:
    """Manages background agent sessions."""
    MAX_SESSIONS = 50  # Prevent unbounded session growth
    
    def __init__(self, sessions_dir: str = ".dev/sessions"):
        self.sessions_dir = os.path.abspath(sessions_dir)
        os.makedirs(self.sessions_dir, exist_ok=True)
        self._sessions_file = os.path.join(self.sessions_dir, "sessions.json")
        self._sessions: dict[str, BackgroundSession] = {}
        self._load()
        self._cleanup_old_sessions()
    
    def _load(self):
        """Load sessions from disk."""
        if os.path.isfile(self._sessions_file):
            try:
                with open(self._sessions_file) as f:
                    data = json.load(f)
                for sid, sdata in data.items():
                    self._sessions[sid] = BackgroundSession(**sdata)
            except Exception:
                self._sessions = {}
    
    def _cleanup_old_sessions(self):
        """Remove old stopped sessions when over limit."""
        if len(self._sessions) <= self.MAX_SESSIONS:
            return
        # Sort by created_at (oldest first)
        sorted_sessions = sorted(
            self._sessions.items(),
            key=lambda kv: kv[1].created_at or ""
        )
        # Remove oldest stopped sessions first
        to_remove = len(self._sessions) - self.MAX_SESSIONS
        for sid, session in sorted_sessions:
            if to_remove <= 0:
                break
            if session.status in ("stopped", "completed", "failed"):
                del self._sessions[sid]
                to_remove -= 1
        self._save()
    
    def _save(self):
        """Save sessions to disk."""
        data = {}
        for sid, session in self._sessions.items():
            data[sid] = {
                "id": session.id,
                "prompt": session.prompt,
                "status": session.status,
                "pid": session.pid,
                "project_path": session.project_path,
                "model": session.model,
                "created_at": session.created_at,
                "stopped_at": session.stopped_at,
                "log_file": session.log_file,
                "error": session.error,
            }
        with open(self._sessions_file, "w") as f:
            json.dump(data, f, indent=2)
    
    def create_session(self, prompt: str, project_path: str = ".", model: str = "default") -> BackgroundSession:
        """Create a new background session."""
        import uuid
        session_id = uuid.uuid4().hex[:12]
        log_file = os.path.join(self.sessions_dir, f"{session_id}.log")
        
        session = BackgroundSession(
            id=session_id,
            prompt=prompt,
            project_path=os.path.abspath(project_path),
            model=model,
            log_file=log_file,
        )
        
        self._sessions[session_id] = session
        self._save()
        return session
    
    def get_session(self, session_id: str) -> Optional[BackgroundSession]:
        """Get a session by ID (supports partial ID matching)."""
        # Exact match first
        if session_id in self._sessions:
            return self._sessions[session_id]
        
        # Partial match
        matches = [s for s in self._sessions if s.startswith(session_id)]
        if len(matches) == 1:
            return self._sessions[matches[0]]
        
        return None
    
    def list_sessions(self, include_completed: bool = False) -> list[BackgroundSession]:
        """List all sessions."""
        sessions = list(self._sessions.values())
        if not include_completed:
            sessions = [s for s in sessions if s.status in ("running", "stopped")]
        return sorted(sessions, key=lambda s: s.created_at, reverse=True)
    
    def stop_session(self, session_id: str) -> bool:
        """Stop a background session."""
        session = self.get_session(session_id)
        if not session:
            return False
        
        if session.pid > 0:
            try:
                os.kill(session.pid, signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
        
        session.status = "stopped"
        session.stopped_at = time.time()
        self._save()
        return True
    
    def respawn_session(self, session_id: str) -> Optional[BackgroundSession]:
        """Restart a stopped session with its conversation intact."""
        old = self.get_session(session_id)
        if not old:
            return None
        
        new = self.create_session(
            prompt=old.prompt,
            project_path=old.project_path,
            model=old.model,
        )
        new.status = "running"
        self._save()
        return new
    
    def remove_session(self, session_id: str) -> bool:
        """Remove a session from the list."""
        session = self.get_session(session_id)
        if not session:
            return False
        
        # Stop if running
        if session.status == "running":
            self.stop_session(session_id)
        
        del self._sessions[session.id]
        self._save()
        
        # Clean up log file
        if session.log_file and os.path.isfile(session.log_file):
            try:
                os.remove(session.log_file)
            except Exception:
                pass
        
        return True
    
    def get_logs(self, session_id: str, lines: int = 50) -> str:
        """Get recent logs from a session."""
        session = self.get_session(session_id)
        if not session:
            return f"Session not found: {session_id}"
        
        if not session.log_file or not os.path.isfile(session.log_file):
            return f"No logs available for session {session.id[:8]}"
        
        try:
            with open(session.log_file, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            return "".join(all_lines[-lines:])
        except Exception as e:
            return f"Error reading logs: {e}"
    
    def write_log(self, session_id: str, message: str):
        """Write a message to a session's log file."""
        session = self.get_session(session_id)
        if session and session.log_file:
            try:
                os.makedirs(os.path.dirname(session.log_file), exist_ok=True)
                with open(session.log_file, "a", encoding="utf-8") as f:
                    f.write(f"[{time.strftime('%H:%M:%S')}] {message}\n")
            except Exception:
                pass
    
    def format_session(self, session: BackgroundSession) -> str:
        """Format a session for display."""
        status_colors = {
            "running": "[green]running[/green]",
            "stopped": "[yellow]stopped[/yellow]",
            "completed": "[green]completed[/green]",
            "failed": "[red]failed[/red]",
        }
        status_str = status_colors.get(session.status, session.status)
        age = time.time() - session.created_at
        if age < 60:
            age_str = f"{age:.0f}s ago"
        elif age < 3600:
            age_str = f"{age/60:.0f}m ago"
        else:
            age_str = f"{age/3600:.1f}h ago"
        
        return f"  {session.id[:12]}  {status_str:20s}  {age_str:10s}  {session.prompt[:50]}"


# ============================================================================
# Auth Manager
# ============================================================================

class AuthManager:
    """Manage Dev authentication (API keys)."""
    
    def __init__(self, config_dir: str = ".dev"):
        self.config_dir = os.path.expanduser("~/.dev") if config_dir == ".dev" else config_dir
        self.config_file = os.path.join(self.config_dir, "config.json")
    
    def _load_config(self) -> dict:
        if os.path.isfile(self.config_file):
            try:
                with open(self.config_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
    
    def _save_config(self, config: dict):
        os.makedirs(self.config_dir, exist_ok=True)
        with open(self.config_file, "w") as f:
            json.dump(config, f, indent=2)
    
    def login(self, key: str, name: str = "default") -> dict:
        """Add an API key (login)."""
        config = self._load_config()
        if "api_keys" not in config:
            config["api_keys"] = []
        if key not in config["api_keys"]:
            config["api_keys"].append(key)
        config["active_key"] = key
        self._save_config(config)
        return {"success": True, "message": f"Key '{name}' added ({len(config['api_keys'])} total)"}
    
    def logout(self) -> dict:
        """Remove active API key (logout)."""
        config = self._load_config()
        if "active_key" in config:
            del config["active_key"]
        self._save_config(config)
        return {"success": True, "message": "Logged out"}
    
    def status(self) -> dict:
        """Show auth status."""
        config = self._load_config()
        keys = config.get("api_keys", [])
        active = config.get("active_key", "")
        return {
            "authenticated": bool(active),
            "key_count": len(keys),
            "active_key": active[:8] + "..." if active else "none",
            "provider": "NVIDIA NIMs (free tier)",
        }
    
    def list_keys(self) -> list[dict]:
        """List all configured keys."""
        config = self._load_config()
        keys = config.get("api_keys", [])
        active = config.get("active_key", "")
        return [
            {"key": k[:8] + "...", "active": k == active}
            for k in keys
        ]


# ============================================================================
# Update Checker
# ============================================================================

class UpdateChecker:
    """Check for and apply updates."""
    
    VERSION = "0.1.0"
    
    @staticmethod
    def check_version() -> dict:
        """Check current version."""
        return {
            "current": UpdateChecker.VERSION,
            "provider": "NVIDIA NIMs (free tier)",
            "message": "Dev is free and open-source. No auto-update needed.",
        }
    
    @staticmethod
    def update() -> dict:
        """Attempt to update."""
        return {
            "success": True,
            "message": f"Dev {UpdateChecker.VERSION} — using NVIDIA NIMs free tier. No updates required.",
        }
