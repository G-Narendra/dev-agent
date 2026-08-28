"""
Session Persistence — Save and Load Conversations

Allows users to save conversations and resume them later.
Sessions are stored in .dev/sessions/
"""
import json
import os
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class Session:
    """A saved conversation session."""
    id: str
    name: str
    created_at: str = ""
    updated_at: str = ""
    messages: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.updated_at = self.created_at


class SessionManager:
    """
    Manage saved conversation sessions.
    
    Sessions are stored in .dev/sessions/<id>.json
    
    Usage:
        manager = SessionManager(project_path=".")
        
        # Save current session
        manager.save("my-session", messages)
        
        # Load a session
        messages = manager.load("my-session")
        
        # List all sessions
        sessions = manager.list_sessions()
    """
    
    MAX_SESSIONS = 100  # Prevent unbounded session growth
    MAX_SESSION_SIZE_MB = 10  # Max size per session file
    
    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
        self.sessions_dir = os.path.join(self.project_path, ".dev", "sessions")
        os.makedirs(self.sessions_dir, exist_ok=True)
        self._cleanup_old_sessions()
    
    def _cleanup_old_sessions(self):
        """Remove old session files when over limit."""
        try:
            session_files = [
                f for f in os.listdir(self.sessions_dir)
                if f.endswith('.json')
            ]
            if len(session_files) <= self.MAX_SESSIONS:
                return
            # Sort by modification time (oldest first)
            session_files.sort(
                key=lambda f: os.path.getmtime(os.path.join(self.sessions_dir, f))
            )
            # Remove oldest files beyond limit
            to_remove = len(session_files) - self.MAX_SESSIONS
            for f in session_files[:to_remove]:
                try:
                    os.remove(os.path.join(self.sessions_dir, f))
                except Exception:
                    pass  # Intentional: non-critical: best-effort operation
        except Exception:
            pass  # Intentional: non-critical: best-effort operation
    
    def _mask_sensitive(self, messages: list) -> list:
        """Mask sensitive data (API keys, passwords) in session messages."""
        import re
        import copy
        masked = copy.deepcopy(messages)
        patterns = [
            (r'nvapi-[A-Za-z0-9_\-]{20,}', 'nvapi-***'),
            (r'sk-[A-Za-z0-9]{20,}', 'sk-***'),
            (r'ghp_[A-Za-z0-9]{20,}', 'ghp_***'),
            (r'(api[_-]?key|secret|password|token)\s*[=:]\s*["\']?([^\s"\']{8,})["\']?', r'\1=***'),
        ]
        for msg in masked:
            if isinstance(msg, dict) and 'content' in msg:
                content = msg['content']
                if isinstance(content, str):
                    for pat, repl in patterns:
                        content = re.sub(pat, repl, content, flags=re.IGNORECASE)
                    msg['content'] = content
        return masked

    def save(self, name: str, messages: list, metadata: dict = None) -> str:
        """
        Save a conversation session.
        
        Args:
            name: Session name
            messages: List of message objects
            metadata: Optional metadata
            
        Returns:
            Session ID
        """
        session_id = name.lower().replace(" ", "-")
        session = Session(
            id=session_id,
            name=name,
            messages=[self._msg_to_dict(m) for m in messages],
            metadata=metadata or {},
        )
        
        path = os.path.join(self.sessions_dir, f"{session_id}.json")
        # Mask sensitive data before saving
        masked_messages = self._mask_sensitive(session.messages)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({
                "id": session.id,
                "name": session.name,
                "created_at": session.created_at,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "messages": masked_messages,
                "metadata": session.metadata,
            }, f, indent=2)
        
        return session_id
    
    def load(self, session_id: str) -> Optional[dict]:
        """
        Load a conversation session.
        
        Returns:
            Session dict with messages, or None if not found
        """
        path = os.path.join(self.sessions_dir, f"{session_id}.json")
        if not os.path.exists(path):
            return None
        
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def list_sessions(self) -> list[dict]:
        """List all saved sessions."""
        sessions = []
        for fname in os.listdir(self.sessions_dir):
            if fname.endswith('.json'):
                try:
                    path = os.path.join(self.sessions_dir, fname)
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    sessions.append({
                        "id": data.get("id", fname[:-5]),
                        "name": data.get("name", fname[:-5]),
                        "created_at": data.get("created_at", ""),
                        "updated_at": data.get("updated_at", ""),
                        "messages": len(data.get("messages", [])),
                    })
                except Exception:
                    pass  # Intentional: non-critical: best-effort operation
        
        return sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True)
    
    def delete(self, session_id: str) -> bool:
        """Delete a session."""
        path = os.path.join(self.sessions_dir, f"{session_id}.json")
        if os.path.exists(path):
            os.remove(path)
            return True
        return False
    
    def search(self, query: str) -> list[dict]:
        """Search sessions by name or content."""
        query_lower = query.lower()
        results = []
        
        for session in self.list_sessions():
            if query_lower in session["name"].lower():
                results.append(session)
            # Also search in message content
            elif session.get("messages"):
                for msg in session["messages"]:
                    content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
                    if query_lower in content.lower():
                        results.append(session)
                        break
        
        return results
    
    def export_session(self, session_id: str, format: str = "markdown") -> str:
        """Export a session to markdown or JSON format."""
        session = self.load(session_id)
        if not session:
            return "Session not found"
        
        if format == "json":
            return json.dumps(session, indent=2, ensure_ascii=False)
        
        # Markdown format
        lines = [f"# Session: {session.get('name', session_id)}", ""]
        lines.append(f"Created: {session.get('created_at', 'unknown')}")
        lines.append("")
        
        for msg in session.get("messages", []):
            role = msg.get("role", "unknown") if isinstance(msg, dict) else "unknown"
            content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
            if content:
                lines.append(f"## {role.title()}")
                lines.append("")
                lines.append(content)
                lines.append("")
        
        return "\n".join(lines)
    
    def tag_session(self, session_id: str, tags: list[str]):
        """Add tags to a session for organization."""
        path = os.path.join(self.sessions_dir, f"{session_id}.json")
        if not os.path.isfile(path):
            return False
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            metadata = data.get("metadata", {})
            existing_tags = metadata.get("tags", [])
            metadata["tags"] = list(set(existing_tags + tags))
            data["metadata"] = metadata
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception:
            return False
    
    def get_analytics(self) -> dict:
        """Get analytics across all sessions."""
        sessions = self.list_sessions()
        if not sessions:
            return {"total_sessions": 0}
        
        total_messages = 0
        all_tags = []
        tool_usage = {}
        
        for session in sessions:
            for msg in session.get("messages", []):
                total_messages += 1
                if isinstance(msg, dict):
                    if msg.get("role") == "assistant" and msg.get("tool_calls"):
                        for tc in msg["tool_calls"]:
                            name = tc.get("function", {}).get("name", "unknown")
                            tool_usage[name] = tool_usage.get(name, 0) + 1
            tags = session.get("metadata", {}).get("tags", [])
            all_tags.extend(tags)
        
        # Count tag usage
        tag_counts = {}
        for tag in all_tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        
        return {
            "total_sessions": len(sessions),
            "total_messages": total_messages,
            "avg_messages_per_session": total_messages // len(sessions) if sessions else 0,
            "tool_usage": dict(sorted(tool_usage.items(), key=lambda x: x[1], reverse=True)[:10]),
            "tags": tag_counts,
        }
    
    def _msg_to_dict(self, msg) -> dict:
        """Convert a message object to dict."""
        if hasattr(msg, '__dict__'):
            return {
                "role": getattr(msg, 'role', 'unknown'),
                "content": getattr(msg, 'content', ''),
                "name": getattr(msg, 'name', None),
                "tool_calls": getattr(msg, 'tool_calls', None),
                "tool_call_id": getattr(msg, 'tool_call_id', None),
            }
        elif isinstance(msg, dict):
            return msg
        return {"role": "unknown", "content": str(msg)}
