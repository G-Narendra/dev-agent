"""
Conversation History System for Dev.

Implements persistent conversation history with compaction.
Adapted from Aider's history.py and Freebuff's context management.

Improvement #4: Conversation history with persistence
Improvement #10: Session resume from checkpoint
"""

from __future__ import annotations

import json
import os
import time
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class ChatMessage:
    """A single chat message."""
    role: str  # system, user, assistant, tool
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    tool_call_id: str = ""
    name: str = ""
    timestamp: float = field(default_factory=time.time)
    tokens: int = 0
    
    def to_dict(self) -> dict:
        d = {"role": self.role, "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.name:
            d["name"] = self.name
        return d
    
    @classmethod
    def from_dict(cls, d: dict) -> ChatMessage:
        return cls(
            role=d.get("role", ""),
            content=d.get("content", ""),
            tool_calls=d.get("tool_calls", []),
            tool_call_id=d.get("tool_call_id", ""),
            name=d.get("name", ""),
        )


@dataclass
class Conversation:
    """A complete conversation with history."""
    id: str
    messages: list[ChatMessage] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)
    
    MAX_MESSAGES = 5000

    def add_message(self, role: str, content: str, **kwargs) -> ChatMessage:
        """Add a message to the conversation."""
        msg = ChatMessage(role=role, content=content, **kwargs)
        self.messages.append(msg)
        # Cap full history to prevent OOM on long sessions
        if len(self.messages) > self.MAX_MESSAGES:
            self.messages = self.messages[-self.MAX_MESSAGES:]
        self.updated_at = time.time()
        return msg
    
    def get_messages(self, limit: int | None = None) -> list[ChatMessage]:
        """Get messages, optionally limited to recent ones."""
        if limit:
            return self.messages[-limit:]
        return self.messages
    
    def total_tokens(self) -> int:
        """Estimate total tokens in conversation."""
        return sum(m.tokens for m in self.messages) or sum(
            len(m.content) // 3 for m in self.messages
        )
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> Conversation:
        return cls(
            id=d.get("id", ""),
            messages=[ChatMessage.from_dict(m) for m in d.get("messages", [])],
            created_at=d.get("created_at", 0),
            updated_at=d.get("updated_at", 0),
            metadata=d.get("metadata", {}),
        )


class ConversationHistory:
    """
    Manages conversation history with persistence.
    
    Features:
    - Save/load conversations to disk
    - Multiple conversation support
    - Auto-compaction when context gets too large
    - Session resume from checkpoint
    """
    
    def __init__(self, history_dir: str | None = None):
        self.history_dir = history_dir or os.path.join(
            os.path.expanduser("~"), ".dev", "conversations"
        )
        os.makedirs(self.history_dir, exist_ok=True)
        self._conversations: dict[str, Conversation] = {}
    
    def create_conversation(self, conv_id: str | None = None) -> Conversation:
        """Create a new conversation."""
        import uuid
        conv_id = conv_id or str(uuid.uuid4())
        conv = Conversation(id=conv_id)
        self._conversations[conv_id] = conv
        return conv
    
    def get_conversation(self, conv_id: str) -> Conversation | None:
        """Get a conversation by ID."""
        if conv_id in self._conversations:
            return self._conversations[conv_id]
        
        # Try loading from disk
        return self.load_conversation(conv_id)
    
    def list_conversations(self) -> list[dict]:
        """List all saved conversations."""
        conversations = []
        for fname in os.listdir(self.history_dir):
            if fname.endswith(".json"):
                try:
                    fpath = os.path.join(self.history_dir, fname)
                    with open(fpath, encoding="utf-8") as f:
                        data = json.load(f)
                    if not isinstance(data, dict):
                        continue
                    conversations.append({
                        "id": data.get("id", fname[:-5]),
                        "updated_at": data.get("updated_at", 0),
                        "message_count": len(data.get("messages", [])),
                        "metadata": data.get("metadata", {}),
                    })
                except Exception:
                    continue
        
        return sorted(conversations, key=lambda x: x["updated_at"], reverse=True)
    
    def save_conversation(self, conv: Conversation) -> str:
        """Save a conversation to disk (atomic write)."""
        fpath = os.path.join(self.history_dir, f"{conv.id}.json")
        temp_fpath = fpath + ".tmp"
        # Create with strict permissions (0600) to prevent credential leakage
        fd = os.open(temp_fpath, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(conv.to_dict(), f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_fpath, fpath)
        return fpath
    
    def load_conversation(self, conv_id: str) -> Conversation | None:
        """Load a conversation from disk."""
        fpath = os.path.join(self.history_dir, f"{conv_id}.json")
        if not os.path.exists(fpath):
            return None
        
        try:
            with open(fpath) as f:
                data = json.load(f)
            conv = Conversation.from_dict(data)
            self._conversations[conv_id] = conv
            return conv
        except Exception:
            return None
    
    def delete_conversation(self, conv_id: str) -> bool:
        """Delete a conversation."""
        fpath = os.path.join(self.history_dir, f"{conv_id}.json")
        if os.path.exists(fpath):
            os.remove(fpath)
        self._conversations.pop(conv_id, None)
        return True
    
    def compact_conversation(
        self,
        conv: Conversation,
        max_tokens: int = 100_000,
        keep_recent: int = 10,
    ) -> Conversation:
        """
        Compact a conversation by summarizing old messages.
        
        From Aider's summarizer pattern:
        - Keep system messages
        - Keep last N messages intact
        - Summarize middle messages
        """
        if conv.total_tokens() <= max_tokens:
            return conv
        
        messages = conv.messages
        if len(messages) <= keep_recent:
            return conv
        
        # Split into: system, old (to summarize), recent (keep)
        system_msgs = [m for m in messages if m.role == "system"]
        non_system = [m for m in messages if m.role != "system"]
        
        if len(non_system) <= keep_recent:
            return conv
        
        old_msgs = non_system[:-keep_recent]
        recent_msgs = non_system[-keep_recent:]
        
        # Create summary of old messages
        summary_parts = []
        for msg in old_msgs:
            if msg.role == "user":
                summary_parts.append(f"User: {msg.content[:200]}")
            elif msg.role == "assistant" and msg.content:
                summary_parts.append(f"Assistant: {msg.content[:200]}")
        
        summary = "[Previous conversation summary]\n" + "\n".join(summary_parts)
        
        # Rebuild conversation
        compacted = Conversation(
            id=conv.id,
            metadata=conv.metadata,
            created_at=conv.created_at,
        )
        
        # Add system messages
        for msg in system_msgs:
            compacted.messages.append(msg)
        
        # Add summary as user message
        compacted.messages.append(ChatMessage(role="user", content=summary))
        compacted.messages.append(ChatMessage(
            role="assistant",
            content="I understand the previous context. Let's continue.",
        ))
        
        # Add recent messages
        compacted.messages.extend(recent_msgs)
        
        return compacted
    
    def get_checkpoint(self, conv: Conversation) -> dict:
        """Save a checkpoint of the conversation."""
        return {
            "conversation_id": conv.id,
            "message_count": len(conv.messages),
            "total_tokens": conv.total_tokens(),
            "timestamp": time.time(),
            "data": conv.to_dict(),
        }
    
    def restore_checkpoint(self, checkpoint: dict) -> Conversation | None:
        """Restore from a checkpoint."""
        return Conversation.from_dict(checkpoint.get("data", {}))


class ContextManager:
    """
    Manages context window for LLM calls.
    
    Features:
    - Token counting and limits
    - Automatic compaction
    - File tracking
    - Multi-file context
    """
    
    def __init__(self, max_tokens: int = 100_000):
        self.max_tokens = max_tokens
        self._files: dict[str, str] = {}  # path -> content
        self._history = ConversationHistory()
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count (~3 chars per token)."""
        return len(text) // 3
    
    def build_context(
        self,
        system_prompt: str,
        messages: list[dict],
        repo_map: str = "",
    ) -> list[dict]:
        """
        Build context that fits within token limits.
        
        Priority:
        1. System prompt (always include)
        2. Repo map (if fits)
        3. Recent messages (keep all)
        4. Old messages (summarize if needed)
        """
        context = []
        tokens_used = 0
        
        # 1. System prompt
        sys_tokens = self.estimate_tokens(system_prompt)
        context.append({"role": "system", "content": system_prompt})
        tokens_used += sys_tokens
        
        # 2. Repo map (if fits)
        if repo_map:
            map_tokens = self.estimate_tokens(repo_map)
            if tokens_used + map_tokens < self.max_tokens * 0.8:
                context.append({"role": "system", "content": f"Repository:\n{repo_map}"})
                tokens_used += map_tokens
        
        # 3. File contents
        for path, content in self._files.items():
            file_tokens = self.estimate_tokens(content)
            if tokens_used + file_tokens < self.max_tokens * 0.9:
                context.append({
                    "role": "system",
                    "content": f"File: {path}\n```\n{content}\n```",
                })
                tokens_used += file_tokens
        
        # 4. Messages (recent first, summarize old)
        recent = messages[-20:]  # Keep last 20 messages
        old = messages[:-20] if len(messages) > 20 else []
        
        # Add recent messages
        for msg in recent:
            msg_tokens = self.estimate_tokens(msg.get("content", ""))
            if tokens_used + msg_tokens < self.max_tokens:
                context.append(msg)
                tokens_used += msg_tokens
        
        # Add summary of old messages if any
        if old:
            summary = self._summarize_messages(old)
            summary_tokens = self.estimate_tokens(summary)
            if tokens_used + summary_tokens < self.max_tokens:
                context.append({"role": "user", "content": f"[Previous context summary]\n{summary}"})
        
        return context
    
    def add_file(self, path: str, content: str):
        """Add a file to the context."""
        self._files[path] = content
    
    def remove_file(self, path: str):
        """Remove a file from context."""
        self._files.pop(path, None)
    
    def clear_files(self):
        """Clear all files from context."""
        self._files.clear()
    
    def _summarize_messages(self, messages: list[dict]) -> str:
        """Create a summary of messages."""
        parts = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                parts.append(f"User asked: {content[:150]}")
            elif role == "assistant" and content:
                parts.append(f"Assistant said: {content[:150]}")
            elif role == "tool":
                parts.append(f"Tool result: {content[:100]}")
        
        return "\n".join(parts[-20:])  # Last 20 items
