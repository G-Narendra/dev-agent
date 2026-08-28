"""
Session module — re-exports from dev.core.session for backward compatibility.
"""

from ..core.session import UnifiedSessionManager, SessionState
from .sessions import SessionManager, Session, SessionStatus


class SessionStore:
    """Alias for SessionManager for backward compatibility."""

    def __init__(self, sessions_dir: str = ".dev/sessions"):
        self.sessions_dir = sessions_dir
        self.manager = UnifiedSessionManager(base_dir=".dev")

    def save(self, session_id: str, data: dict):
        """Save session data."""
        sess = self.manager.get_session(session_id) or self.manager.create_session()
        sess.messages = data.get("messages", [])
        sess.metadata = data.get("metadata", {})
        self.manager.save_session_detail(sess)

    def load(self, session_id: str) -> dict:
        """Load session data."""
        sess = self.manager.get_session(session_id)
        if not sess:
            return {}
        return {"messages": sess.messages, "metadata": sess.metadata}

    def list_all(self) -> list:
        """List all sessions."""
        return [s.session_id for s in self.manager.list_sessions()]

    def delete(self, session_id: str) -> bool:
        """Delete a session."""
        return self.manager.delete_session(session_id)


__all__ = [
    "SessionManager",
    "Session",
    "SessionStatus",
    "SessionStore",
    "UnifiedSessionManager",
    "SessionState",
]
