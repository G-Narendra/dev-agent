"""
Auto memory system.

Like Claude Code's auto memory:
- Agent automatically writes learnings to .dev/memory/
- Loaded at start of every session
- Covers build commands, debugging insights, preferences
"""
from __future__ import annotations
import os
import json
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class MemoryEntry:
    """A single memory entry."""
    key: str
    value: str
    category: str = "general"  # build, debug, preference, pattern, command
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_used: Optional[str] = None
    use_count: int = 0


class AutoMemory:
    """Automatic memory system that persists learnings across sessions."""
    MAX_ENTRIES = 500  # Prevent unbounded growth
    
    def __init__(self, project_root: str = "."):
        self.project_root = os.path.abspath(project_root)
        self.memory_dir = os.path.join(self.project_root, ".dev", "memory")
        self.memory_file = os.path.join(self.memory_dir, "auto_memory.md")
        self.index_file = os.path.join(self.memory_dir, "index.json")
        os.makedirs(self.memory_dir, exist_ok=True)
        self.entries: dict[str, MemoryEntry] = {}
        self._load()
        self._cleanup_if_needed()

    def _load(self):
        """Load memory from disk."""
        if os.path.exists(self.index_file):
            with open(self.index_file) as f:
                data = json.load(f)
            for key, entry_data in data.get("entries", {}).items():
                self.entries[key] = MemoryEntry(
                    key=key,
                    value=entry_data["value"],
                    category=entry_data.get("category", "general"),
                    created_at=entry_data.get("created_at", ""),
                    last_used=entry_data.get("last_used"),
                    use_count=entry_data.get("use_count", 0),
                )

    def _cleanup_if_needed(self):
        """Remove oldest/least-used entries when over limit."""
        if len(self.entries) <= self.MAX_ENTRIES:
            return
        # Sort by use_count (ascending) then by last_used (oldest first)
        sorted_entries = sorted(
            self.entries.items(),
            key=lambda kv: (kv[1].use_count, kv[1].last_used or "")
        )
        # Remove oldest 20%
        to_remove = len(self.entries) - int(self.MAX_ENTRIES * 0.8)
        for key, _ in sorted_entries[:to_remove]:
            del self.entries[key]
        self._save()

    def _save(self):
        """Save memory to disk."""
        data = {
            "entries": {
                key: {
                    "value": e.value,
                    "category": e.category,
                    "created_at": e.created_at,
                    "last_used": e.last_used,
                    "use_count": e.use_count,
                }
                for key, e in self.entries.items()
            }
        }
        with open(self.index_file, "w") as f:
            json.dump(data, f, indent=2)
        
        # Also write human-readable markdown
        self._write_markdown()

    def _write_markdown(self):
        """Write memory as readable markdown."""
        lines = ["# Auto Memory", f"_Last updated: {datetime.now().isoformat()}_", ""]
        
        categories = {}
        for entry in self.entries.values():
            if entry.category not in categories:
                categories[entry.category] = []
            categories[entry.category].append(entry)
        
        for cat, entries in sorted(categories.items()):
            lines.append(f"## {cat.title()}")
            for e in sorted(entries, key=lambda x: x.use_count, reverse=True):
                lines.append(f"- **{e.key}**: {e.value}")
            lines.append("")
        
        with open(self.memory_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def remember(self, key: str, value: str, category: str = "general"):
        """Store a learning."""
        self.entries[key] = MemoryEntry(
            key=key,
            value=value,
            category=category,
        )
        self._save()

    def recall(self, key: str) -> Optional[str]:
        """Recall a learning by key."""
        entry = self.entries.get(key)
        if entry:
            entry.last_used = datetime.now().isoformat()
            entry.use_count += 1
            self._save()
            return entry.value
        return None

    def forget(self, key: str) -> bool:
        """Remove a learning."""
        if key in self.entries:
            del self.entries[key]
            self._save()
            return True
        return False

    def search(self, query: str) -> list[MemoryEntry]:
        """Search memories by query."""
        results = []
        query_lower = query.lower()
        for entry in self.entries.values():
            if query_lower in entry.key.lower() or query_lower in entry.value.lower():
                results.append(entry)
        return results

    def get_by_category(self, category: str) -> list[MemoryEntry]:
        """Get all memories in a category."""
        return [e for e in self.entries.values() if e.category == category]

    def get_context_prompt(self, max_chars: int = 2000) -> str:
        """Get memory as context for the LLM."""
        if not self.entries:
            return ""
        
        lines = ["## Auto Memory (learned from previous sessions)"]
        total = 0
        for entry in sorted(self.entries.values(), key=lambda x: x.use_count, reverse=True):
            line = f"- [{entry.category}] {entry.key}: {entry.value}"
            if total + len(line) > max_chars:
                break
            lines.append(line)
            total += len(line)
        
        return "\n".join(lines)

    def learn_from_interaction(self, user_feedback: str, context: str = ""):
        """Automatically learn from user feedback/corrections."""
        feedback_lower = user_feedback.lower()
        
        # Detect build commands
        if any(kw in feedback_lower for kw in ["build", "compile", "make", "npm run", "cargo build"]):
            self.remember("build_command", user_feedback, "build")
        
        # Detect test commands
        elif any(kw in feedback_lower for kw in ["test", "pytest", "jest", "cargo test"]):
            self.remember("test_command", user_feedback, "test")
        
        # Detect debugging patterns
        elif any(kw in feedback_lower for kw in ["debug", "error", "fix", "broken", "bug"]):
            key = f"debug_{len(self.entries)}"
            self.remember(key, f"{context}: {user_feedback}" if context else user_feedback, "debug")
        
        # Detect preferences
        elif any(kw in feedback_lower for kw in ["prefer", "always", "never", "use", "don't use"]):
            key = f"pref_{len(self.entries)}"
            self.remember(key, user_feedback, "preference")
        
        # Detect patterns
        elif any(kw in feedback_lower for kw in ["pattern", "convention", "style", "format"]):
            key = f"pattern_{len(self.entries)}"
            self.remember(key, user_feedback, "pattern")

    def list_all(self) -> list[dict]:
        """List all memories."""
        return [
            {
                "key": e.key,
                "value": e.value[:100],
                "category": e.category,
                "use_count": e.use_count,
            }
            for e in sorted(self.entries.values(), key=lambda x: x.use_count, reverse=True)
        ]

    def clear(self):
        """Clear all memories."""
        self.entries.clear()
        self._save()
