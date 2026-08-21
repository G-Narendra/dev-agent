"""
Session persistence for Dev.

From Freebuff's chat-history-store.ts and Aider's history.py.
Saves and loads conversation history for resuming sessions.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional


@dataclass
class SessionMetadata:
    """Session metadata."""
    id: str = ""
    name: str = ""
    created_at: float = 0
    updated_at: float = 0
    model: str = ""
    project_path: str = ""
    message_count: int = 0
    total_tokens: int = 0


@dataclass
class SessionData:
    """Full session data."""
    metadata: SessionMetadata = field(default_factory=SessionMetadata)
    messages: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    file_context: dict[str, str] = field(default_factory=dict)


class SessionStore:
    """
    Persistent session storage.
    
    From Freebuff's chat-history-store.ts.
    Stores sessions in ~/.dev/sessions/
    """
    
    def __init__(self, sessions_dir: str | None = None):
        self.sessions_dir = sessions_dir or os.path.expanduser("~/.dev/sessions")
        os.makedirs(self.sessions_dir, exist_ok=True)
    
    def create_session(self, name: str = "", model: str = "", project_path: str = "") -> str:
        """Create a new session and return its ID."""
        session_id = str(uuid.uuid4())[:8]
        
        metadata = SessionMetadata(
            id=session_id,
            name=name or f"session-{session_id}",
            created_at=time.time(),
            updated_at=time.time(),
            model=model,
            project_path=project_path,
        )
        
        session = SessionData(metadata=metadata)
        self._save(session)
        
        return session_id
    
    def load_session(self, session_id: str) -> SessionData | None:
        """Load a session by ID."""
        session_file = os.path.join(self.sessions_dir, f"{session_id}.json")
        
        if not os.path.exists(session_file):
            return None
        
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            metadata = SessionMetadata(**data.get("metadata", {}))
            messages = data.get("messages", [])
            tool_calls = data.get("tool_calls", [])
            file_context = data.get("file_context", {})
            
            return SessionData(
                metadata=metadata,
                messages=messages,
                tool_calls=tool_calls,
                file_context=file_context,
            )
        except Exception:
            return None
    
    def save_session(self, session: SessionData):
        """Save a session."""
        session.metadata.updated_at = time.time()
        session.metadata.message_count = len(session.messages)
        self._save(session)
    
    def _save(self, session: SessionData):
        """Internal save method."""
        session_file = os.path.join(self.sessions_dir, f"{session.metadata.id}.json")
        
        data = {
            "metadata": asdict(session.metadata),
            "messages": session.messages,
            "tool_calls": session.tool_calls,
            "file_context": session.file_context,
        }
        
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def list_sessions(self, limit: int = 20) -> list[SessionMetadata]:
        """List recent sessions."""
        sessions = []
        
        for filename in os.listdir(self.sessions_dir):
            if filename.endswith(".json"):
                session_id = filename[:-5]
                session = self.load_session(session_id)
                if session:
                    sessions.append(session.metadata)
        
        # Sort by updated_at (most recent first)
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        
        return sessions[:limit]
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        session_file = os.path.join(self.sessions_dir, f"{session_id}.json")
        
        if os.path.exists(session_file):
            os.remove(session_file)
            return True
        return False
    
    def get_recent_session(self, project_path: str = "") -> SessionData | None:
        """Get the most recent session for a project."""
        sessions = self.list_sessions(limit=50)
        
        for metadata in sessions:
            if project_path and metadata.project_path != project_path:
                continue
            return self.load_session(metadata.id)
        
        return None


class SessionConversationManager:
    """
    Manages conversation history within a session.
    
    From Aider's done_messages/cur_messages pattern.
    """
    
    def __init__(self, session: SessionData | None = None):
        self.session = session or SessionData()
        self._current_messages: list[dict] = []
    
    @property
    def messages(self) -> list[dict]:
        """All messages (done + current)."""
        return self.session.messages + self._current_messages
    
    @property
    def current_messages(self) -> list[dict]:
        """Current turn messages."""
        return self._current_messages
    
    def add_user_message(self, content: str):
        """Add a user message."""
        self._current_messages.append({
            "role": "user",
            "content": content,
            "timestamp": time.time(),
        })
    
    def add_assistant_message(self, content: str, tool_calls: list[dict] | None = None):
        """Add an assistant message."""
        msg = {
            "role": "assistant",
            "content": content,
            "timestamp": time.time(),
        }
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self._current_messages.append(msg)
    
    def add_tool_result(self, tool_call_id: str, name: str, content: str):
        """Add a tool result message."""
        self._current_messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": content,
            "timestamp": time.time(),
        })
    
    def end_turn(self):
        """End the current turn and move messages to done."""
        self.session.messages.extend(self._current_messages)
        self._current_messages = []
    
    def clear(self):
        """Clear all messages."""
        self.session.messages.clear()
        self._current_messages.clear()
    
    def get_summary(self, max_tokens: int = 1000) -> str:
        """Get a summary of the conversation."""
        total_chars = sum(len(m.get("content", "")) for m in self.messages)
        
        if total_chars < max_tokens * 3:
            # Short enough to include fully
            parts = []
            for msg in self.messages:
                role = msg.get("role", "").upper()
                content = msg.get("content", "")[:200]
                parts.append(f"{role}: {content}")
            return "\n".join(parts)
        else:
            # Summarize
            recent = self.messages[-5:]
            parts = ["[Conversation summary]"]
            for msg in recent:
                role = msg.get("role", "").upper()
                content = msg.get("content", "")[:100]
                parts.append(f"{role}: {content}")
            return "\n".join(parts)
