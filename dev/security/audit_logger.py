"""
Audit Logger — Teleport-style audit trail for all agent actions.

Logs:
- Every tool invocation with parameters and results
- Every LLM call with token usage
- Every file modification with diff
- Every security event (injection detected, denied tool call)
- Compaction events
- Session lifecycle events

All logs are structured JSON for easy querying.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional
from enum import Enum


class AuditEventType(Enum):
    """Types of audit events."""
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    LLM_CALL = "llm_call"
    LLM_RESPONSE = "llm_response"
    FILE_MODIFY = "file_modify"
    FILE_READ = "file_read"
    SECURITY_EVENT = "security_event"
    COMPACTION = "compaction"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    ERROR = "error"
    USER_ACTION = "user_action"


@dataclass
class AuditEvent:
    """A single audit event."""
    event_type: str
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    tool_result: str = ""
    success: bool = True
    error: str = ""
    tokens_used: int = 0
    duration_ms: float = 0
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "timestamp_human": time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp)
            ),
            "session_id": self.session_id,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "tool_result": self.tool_result[:500],  # Truncate for log
            "success": self.success,
            "error": self.error,
            "tokens_used": self.tokens_used,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }


class AuditLogger:
    """
    Structured audit logger for the Dev agent.
    
    Writes JSON-line logs to .dev/audit/ directory.
    """
    
    def __init__(self, project_path: str = ".", session_id: str = ""):
        self.project_path = Path(project_path)
        self.session_id = session_id or f"session_{int(time.time())}"
        self._log_dir = self.project_path / ".dev" / "audit"
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self._log_dir / f"{self.session_id}.jsonl"
        self._event_count = 0
        self._start_time = time.time()
    
    def log(self, event: AuditEvent):
        """Write an audit event to the log file."""
        event.session_id = self.session_id
        self._event_count += 1
        
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
        except Exception:
            pass  # Don't crash on audit log failure
    
    def log_tool_call(
        self, 
        tool_name: str, 
        tool_args: dict, 
        success: bool = True,
        result: str = "",
        duration_ms: float = 0,
        error: str = "",
    ):
        """Log a tool invocation."""
        self.log(AuditEvent(
            event_type=AuditEventType.TOOL_CALL.value,
            tool_name=tool_name,
            tool_args=self._sanitize_args(tool_args),
            success=success,
            tool_result=result[:500],
            duration_ms=duration_ms,
            error=error,
        ))
    
    def log_llm_call(
        self,
        model: str = "",
        tokens_sent: int = 0,
        tokens_received: int = 0,
        duration_ms: float = 0,
        success: bool = True,
        error: str = "",
    ):
        """Log an LLM API call."""
        self.log(AuditEvent(
            event_type=AuditEventType.LLM_CALL.value,
            success=success,
            tokens_used=tokens_sent + tokens_received,
            duration_ms=duration_ms,
            error=error,
            metadata={"model": model, "tokens_sent": tokens_sent, "tokens_received": tokens_received},
        ))
    
    def log_security_event(
        self,
        event_type: str,
        details: str,
        threat_level: str = "medium",
        blocked: bool = False,
    ):
        """Log a security event."""
        self.log(AuditEvent(
            event_type=AuditEventType.SECURITY_EVENT.value,
            error=details,
            success=not blocked,
            metadata={
                "security_event_type": event_type,
                "threat_level": threat_level,
                "blocked": blocked,
            },
        ))
    
    def log_compaction(
        self,
        original_tokens: int,
        compacted_tokens: int,
        messages_removed: int,
    ):
        """Log a compaction event."""
        self.log(AuditEvent(
            event_type=AuditEventType.COMPACTION.value,
            metadata={
                "original_tokens": original_tokens,
                "compacted_tokens": compacted_tokens,
                "tokens_saved": original_tokens - compacted_tokens,
                "messages_removed": messages_removed,
            },
        ))
    
    def log_file_modify(self, path: str, action: str = "write"):
        """Log a file modification."""
        self.log(AuditEvent(
            event_type=AuditEventType.FILE_MODIFY.value,
            tool_name=action,
            metadata={"file_path": path},
        ))
    
    def log_session_start(self):
        """Log session start."""
        self.log(AuditEvent(
            event_type=AuditEventType.SESSION_START.value,
            metadata={"project_path": str(self.project_path)},
        ))
    
    def log_session_end(self):
        """Log session end."""
        duration = time.time() - self._start_time
        self.log(AuditEvent(
            event_type=AuditEventType.SESSION_END.value,
            metadata={
                "duration_seconds": round(duration, 2),
                "total_events": self._event_count,
            },
        ))
    
    def get_recent_events(self, count: int = 50) -> list[dict]:
        """Read recent audit events."""
        try:
            if not self._log_file.exists():
                return []
            lines = self._log_file.read_text(encoding="utf-8").strip().split("\n")
            events = []
            for line in lines[-count:]:
                if line.strip():
                    events.append(json.loads(line))
            return events
        except Exception:
            return []
    
    def get_security_events(self) -> list[dict]:
        """Get all security-related events."""
        events = self.get_recent_events(1000)
        return [e for e in events if e.get("event_type") == "security_event"]
    
    def _sanitize_args(self, args: dict) -> dict:
        """Sanitize tool arguments for logging (remove secrets)."""
        sanitized = {}
        for key, value in args.items():
            if isinstance(value, str):
                # Redact potential secrets
                if any(word in key.lower() for word in ["key", "secret", "password", "token"]):
                    sanitized[key] = "[REDACTED]"
                elif "nvapi-" in value or "sk-or-" in value or "sk-" in value:
                    sanitized[key] = "[REDACTED]"
                else:
                    sanitized[key] = value[:200]
            else:
                sanitized[key] = str(value)[:200]
        return sanitized
    
    @property
    def stats(self) -> dict:
        """Return audit statistics."""
        return {
            "session_id": self.session_id,
            "total_events": self._event_count,
            "duration_seconds": round(time.time() - self._start_time, 2),
            "log_file": str(self._log_file),
        }
