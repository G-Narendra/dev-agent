"""
Approval modes for Dev agent.

Every major CLI coding tool (Claude Code, Codex, Cline) has approval modes:
- suggest: Show what would change, ask before every edit/command
- auto-edit: Auto-apply file edits, but ask before running commands
- full-auto: Auto-apply everything (dangerous but fast)
"""
from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable, Any
import json
import os


class ApprovalMode(str, Enum):
    SUGGEST = "suggest"       # Ask before everything
    AUTO_EDIT = "auto-edit"   # Auto file edits, ask commands
    FULL_AUTO = "full-auto"   # Auto everything


@dataclass
class ApprovalRequest:
    """A pending approval request."""
    id: str
    mode: str               # "file_edit", "command", "git_push", "deploy", "install"
    description: str
    details: Optional[str] = None
    auto_approved: bool = False
    approved: Optional[bool] = None  # None = pending, True = approved, False = rejected


@dataclass
class ApprovalManager:
    """Manages approval of agent actions based on mode."""
    mode: ApprovalMode = ApprovalMode.SUGGEST
    pending: list = field(default_factory=list)
    history: list = field(default_factory=list)
    auto_approve_patterns: list = field(default_factory=list)  # regex patterns for auto-approve
    _callback: Optional[Callable] = None  # callback for interactive approval

    def set_mode(self, mode: str) -> ApprovalMode:
        """Set the approval mode."""
        try:
            self.mode = ApprovalMode(mode)
        except ValueError:
            self.mode = ApprovalMode.SUGGEST
        return self.mode

    def set_callback(self, callback: Callable):
        """Set callback for interactive approval (async callable that returns bool)."""
        self._callback = callback

    def needs_approval(self, action_type: str, details: str = "") -> bool:
        """Check if an action needs user approval."""
        if self.mode == ApprovalMode.FULL_AUTO:
            # Check auto-approve patterns
            for pattern in self.auto_approve_patterns:
                if pattern in details:
                    return False
            # Full auto: only ask for truly dangerous things
            return action_type in ("git_push", "deploy", "install_global", "delete_production")
        
        if self.mode == ApprovalMode.AUTO_EDIT:
            # Auto-edit: auto file edits, ask for commands and dangerous ops
            if action_type in ("file_edit", "file_write", "file_delete"):
                return False
            if action_type in ("git_push", "deploy", "install_global", "delete_production"):
                return True
            # Commands: ask unless they're read-only
            read_only_cmds = ["ls", "cat", "head", "tail", "grep", "find", "wc", "echo", "pwd", "git status", "git log", "git diff"]
            for cmd in read_only_cmds:
                if details.strip().startswith(cmd):
                    return False
            return True
        
        # SUGGEST mode: ask for everything
        return True

    async def request_approval(self, action_type: str, description: str, details: str = "") -> bool:
        """Request approval for an action. Returns True if approved."""
        if not self.needs_approval(action_type, details):
            req = ApprovalRequest(
                id=f"auto-{len(self.history)}",
                mode=action_type,
                description=description,
                details=details,
                auto_approved=True,
                approved=True,
            )
            self.history.append(req)
            return True

        req = ApprovalRequest(
            id=f"req-{len(self.history)}",
            mode=action_type,
            description=description,
            details=details,
        )
        self.pending.append(req)

        # If we have a callback (interactive mode), use it
        if self._callback:
            approved = await self._callback(req)
            req.approved = approved
            self.pending.remove(req)
            self.history.append(req)
            return approved

        # No callback: auto-reject in suggest mode
        req.approved = False
        self.pending.remove(req)
        self.history.append(req)
        return False

    def approve(self, request_id: str) -> bool:
        """Manually approve a pending request."""
        for req in self.pending:
            if req.id == request_id:
                req.approved = True
                self.pending.remove(req)
                self.history.append(req)
                return True
        return False

    def reject(self, request_id: str) -> bool:
        """Manually reject a pending request."""
        for req in self.pending:
            if req.id == request_id:
                req.approved = False
                self.pending.remove(req)
                self.history.append(req)
                return True
        return False

    def approve_all(self):
        """Approve all pending requests."""
        for req in self.pending[:]:
            req.approved = True
            self.history.append(req)
        self.pending.clear()

    def reject_all(self):
        """Reject all pending requests."""
        for req in self.pending[:]:
            req.approved = False
            self.history.append(req)
        self.pending.clear()

    def add_auto_approve_pattern(self, pattern: str):
        """Add a pattern that auto-approves matching actions."""
        self.auto_approve_patterns.append(pattern)

    def get_stats(self) -> dict:
        """Get approval statistics."""
        total = len(self.history)
        approved = sum(1 for r in self.history if r.approved)
        rejected = total - approved
        auto = sum(1 for r in self.history if r.auto_approved)
        return {
            "mode": self.mode.value,
            "total_requests": total,
            "approved": approved,
            "rejected": rejected,
            "auto_approved": auto,
            "pending": len(self.pending),
        }

    def save_state(self, path: str = ".dev/approval_state.json"):
        """Save approval state to disk."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        state = {
            "mode": self.mode.value,
            "auto_approve_patterns": self.auto_approve_patterns,
            "stats": self.get_stats(),
        }
        with open(path, "w") as f:
            json.dump(state, f, indent=2)

    def load_state(self, path: str = ".dev/approval_state.json"):
        """Load approval state from disk."""
        if os.path.exists(path):
            with open(path) as f:
                state = json.load(f)
            self.mode = ApprovalMode(state.get("mode", "suggest"))
            self.auto_approve_patterns = state.get("auto_approve_patterns", [])


def get_mode_description(mode: ApprovalMode) -> str:
    """Get human-readable description of approval mode."""
    descriptions = {
        ApprovalMode.SUGGEST: (
            "SUGGEST mode: Shows all changes before applying. "
            "You approve every file edit and command."
        ),
        ApprovalMode.AUTO_EDIT: (
            "AUTO-EDIT mode: File edits are applied automatically. "
            "Commands require your approval."
        ),
        ApprovalMode.FULL_AUTO: (
            "FULL-AUTO mode: Everything runs automatically. "
            "Use with caution - no approval prompts."
        ),
    }
    return descriptions.get(mode, "Unknown mode")
