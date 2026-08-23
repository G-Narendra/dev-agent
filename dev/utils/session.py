"""
Session module — re-exports for backward compatibility.
"""
from .sessions import SessionManager, Session, SessionStatus


class SessionStore:
    """Alias for SessionManager for backward compatibility."""
    
    def __init__(self, sessions_dir: str = ".dev/sessions"):
        self.sessions_dir = sessions_dir
        self.manager = SessionManager(project_path=".")
    
    def save(self, session_id: str, data: dict):
        """Save session data."""
        self.manager.save(session_id, data.get("messages", []), data.get("metadata", {}))
    
    def load(self, session_id: str) -> dict:
        """Load session data."""
        return self.manager.load(session_id) or {}
    
    def list_all(self) -> list:
        """List all sessions."""
        return self.manager.list_sessions()
    
    def delete(self, session_id: str) -> bool:
        """Delete a session."""
        return self.manager.delete(session_id)


__all__ = ["SessionManager", "Session", "SessionStatus", "SessionStore"]
