"""
Cross-Session Messaging for Dev Agent.

Allows multiple Dev Agent sessions to communicate with each other
via local IPC (inter-process communication).

Similar to Claude Code's cross-session messaging feature.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from .base import Tool


class SessionMessenger:
    """Local IPC messenger for Dev Agent sessions."""
    
    def __init__(self, session_id: str, project_path: str = "."):
        self.session_id = session_id
        self.project_path = project_path
        self.mailbox_dir = os.path.join(project_path, ".dev", "mailbox")
        os.makedirs(self.mailbox_dir, exist_ok=True)
    
    def send(self, to_session: str, message: str, msg_type: str = "message") -> dict:
        """Send a message to another session."""
        msg = {
            "id": str(uuid.uuid4()),
            "from": self.session_id,
            "to": to_session,
            "type": msg_type,
            "message": message,
            "timestamp": time.time(),
            "read": False,
        }
        
        # Write to recipient's mailbox
        inbox_path = os.path.join(self.mailbox_dir, f"{to_session}.json")
        
        messages = []
        if os.path.exists(inbox_path):
            try:
                with open(inbox_path, "r") as f:
                    messages = json.load(f)
            except (json.JSONDecodeError, IOError):
                messages = []
        
        messages.append(msg)
        
        with open(inbox_path, "w") as f:
            json.dump(messages, f, indent=2)
        
        return {"success": True, "message_id": msg["id"]}
    
    def receive(self) -> list[dict]:
        """Receive all unread messages for this session."""
        inbox_path = os.path.join(self.mailbox_dir, f"{self.session_id}.json")
        
        if not os.path.exists(inbox_path):
            return []
        
        try:
            with open(inbox_path, "r") as f:
                messages = json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
        
        # Get unread messages
        unread = [m for m in messages if not m.get("read", False)]
        
        # Mark as read
        for msg in messages:
            msg["read"] = True
        
        with open(inbox_path, "w") as f:
            json.dump(messages, f, indent=2)
        
        return unread
    
    def list_sessions(self) -> list[str]:
        """List all active sessions with mailboxes."""
        if not os.path.exists(self.mailbox_dir):
            return []
        
        sessions = []
        for filename in os.listdir(self.mailbox_dir):
            if filename.endswith(".json"):
                session_id = filename[:-5]  # Remove .json
                sessions.append(session_id)
        
        return sessions
    
    def broadcast(self, message: str, msg_type: str = "broadcast") -> dict:
        """Send a message to all active sessions."""
        sessions = self.list_sessions()
        sent = 0
        
        for session_id in sessions:
            if session_id != self.session_id:
                self.send(session_id, message, msg_type)
                sent += 1
        
        return {"success": True, "sent_to": sent}


class SendMessageTool(Tool):
    """Send a message to another Dev Agent session."""
    
    name = "send_session_message"
    description = "Send a message to another Dev Agent session running in the same project."
    parameters = {
        "type": "object",
        "properties": {
            "to_session": {"type": "string", "description": "Target session ID"},
            "message": {"type": "string", "description": "Message to send"},
            "type": {"type": "string", "description": "Message type", "default": "message"},
        },
        "required": ["to_session", "message"],
    }
    
    def __init__(self, session_id: str = "", project_path: str = "."):
        self._session_id = session_id or str(uuid.uuid4())[:8]
        self._project_path = project_path
    
    async def execute(self, args: dict) -> dict:
        to_session = args.get("to_session", "")
        message = args.get("message", "")
        msg_type = args.get("type", "message")
        
        if not to_session or not message:
            return {"success": False, "error": "to_session and message are required"}
        
        messenger = SessionMessenger(self._session_id, self._project_path)
        result = messenger.send(to_session, message, msg_type)
        
        return {
            "success": True,
            "message_id": result.get("message_id"),
            "to": to_session,
        }


class ReceiveMessagesTool(Tool):
    """Receive messages from other Dev Agent sessions."""
    
    name = "receive_session_messages"
    description = "Receive unread messages from other Dev Agent sessions."
    parameters = {
        "type": "object",
        "properties": {},
    }
    
    def __init__(self, session_id: str = "", project_path: str = "."):
        self._session_id = session_id or str(uuid.uuid4())[:8]
        self._project_path = project_path
    
    async def execute(self, args: dict) -> dict:
        messenger = SessionMessenger(self._session_id, self._project_path)
        messages = messenger.receive()
        
        return {
            "success": True,
            "count": len(messages),
            "messages": messages,
        }


class ListSessionsTool(Tool):
    """List all active Dev Agent sessions."""
    
    name = "list_sessions"
    description = "List all active Dev Agent sessions in this project."
    parameters = {
        "type": "object",
        "properties": {},
    }
    
    def __init__(self, session_id: str = "", project_path: str = "."):
        self._session_id = session_id or str(uuid.uuid4())[:8]
        self._project_path = project_path
    
    async def execute(self, args: dict) -> dict:
        messenger = SessionMessenger(self._session_id, self._project_path)
        sessions = messenger.list_sessions()
        
        return {
            "success": True,
            "sessions": sessions,
            "count": len(sessions),
        }


class BroadcastTool(Tool):
    """Broadcast a message to all active sessions."""
    
    name = "broadcast_session_message"
    description = "Broadcast a message to all active Dev Agent sessions."
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Message to broadcast"},
            "type": {"type": "string", "description": "Message type", "default": "broadcast"},
        },
        "required": ["message"],
    }
    
    def __init__(self, session_id: str = "", project_path: str = "."):
        self._session_id = session_id or str(uuid.uuid4())[:8]
        self._project_path = project_path
    
    async def execute(self, args: dict) -> dict:
        message = args.get("message", "")
        msg_type = args.get("type", "broadcast")
        
        if not message:
            return {"success": False, "error": "message is required"}
        
        messenger = SessionMessenger(self._session_id, self._project_path)
        result = messenger.broadcast(message, msg_type)
        
        return {
            "success": True,
            "sent_to": result.get("sent_to", 0),
        }


# Export all session messaging tools
SESSION_MESSAGING_TOOLS = [
    SendMessageTool,
    ReceiveMessagesTool,
    ListSessionsTool,
    BroadcastTool,
]
