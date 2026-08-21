"""
Per-tool configurable allow/deny rules.

Like Claude Code's --allowedTools and Cline's per-tool rules:
- Glob pattern matching on tool names
- Configurable via .dev/tool_rules.json or CLI flags
- Supports allow/deny lists with patterns
"""

from __future__ import annotations

import fnmatch
import json
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ToolRule:
    """A rule for tool permission."""
    pattern: str  # fnmatch pattern (e.g., "write_file", "run_terminal_command", "git_*")
    action: str = "allow"  # "allow" or "deny"
    reason: str = ""
    scope: str = "global"  # "global", "session", "project"


class ToolRulesManager:
    """Manages per-tool allow/deny rules."""

    def __init__(self, project_root: str = "."):
        self.project_root = os.path.abspath(project_root)
        self.rules: list[ToolRule] = []
        self._config_path = os.path.join(self.project_root, ".dev", "tool_rules.json")
        self._load_rules()

    def _load_rules(self):
        """Load rules from disk."""
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path) as f:
                    data = json.load(f)
                for r in data.get("rules", []):
                    self.rules.append(ToolRule(
                        pattern=r["pattern"],
                        action=r.get("action", "allow"),
                        reason=r.get("reason", ""),
                        scope=r.get("scope", "global"),
                    ))
            except Exception:
                pass

    def _save_rules(self):
        """Save rules to disk."""
        os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
        data = {
            "rules": [
                {
                    "pattern": r.pattern,
                    "action": r.action,
                    "reason": r.reason,
                    "scope": r.scope,
                }
                for r in self.rules
            ]
        }
        with open(self._config_path, "w") as f:
            json.dump(data, f, indent=2)

    def add_rule(self, pattern: str, action: str = "allow", reason: str = "", scope: str = "global"):
        """Add a tool rule."""
        self.rules.append(ToolRule(pattern=pattern, action=action, reason=reason, scope=scope))
        self._save_rules()

    def remove_rule(self, pattern: str):
        """Remove rules matching a pattern."""
        self.rules = [r for r in self.rules if r.pattern != pattern]
        self._save_rules()

    def check_tool(self, tool_name: str) -> dict:
        """
        Check if a tool is allowed by the rules.

        Returns {"allowed": True/False, "reason": "...", "matched_rule": "..."}
        Rules are evaluated in order (first match wins).
        """
        for rule in self.rules:
            if fnmatch.fnmatch(tool_name, rule.pattern):
                return {
                    "allowed": rule.action == "allow",
                    "reason": rule.reason or f"Rule: {rule.action} {rule.pattern}",
                    "matched_rule": rule.pattern,
                }

        # No rules matched — default allow
        return {"allowed": True, "reason": "No matching rule", "matched_rule": None}

    def add_defaults(self):
        """Add sensible default rules."""
        # Dangerous commands — deny by default
        self.add_rule("run_terminal_command:rm -rf*", "deny", "Recursive delete is dangerous")
        self.add_rule("run_terminal_command:mkfs*", "deny", "Format disk is dangerous")
        self.add_rule("run_terminal_command:dd if=*", "deny", "Raw disk write is dangerous")

        # File operations — allow by default
        self.add_rule("read_files", "allow", "Reading files is safe")
        self.add_rule("write_file", "allow")
        self.add_rule("str_replace", "allow")
        self.add_rule("code_search", "allow")
        self.add_rule("glob", "allow")
        self.add_rule("list_directory", "allow")
        self.add_rule("git_operations", "allow")
        self.add_rule("web_search", "allow")
        self.add_rule("read_url", "allow")

    def list_rules(self) -> list[dict]:
        """List all rules."""
        return [
            {
                "pattern": r.pattern,
                "action": r.action,
                "reason": r.reason,
                "scope": r.scope,
            }
            for r in self.rules
        ]

    def setup_from_cli_args(self, allowed_tools: list[str] | None = None,
                            denied_tools: list[str] | None = None):
        """Set up rules from CLI --allowedTools / --deniedTools flags."""
        if allowed_tools:
            for pattern in allowed_tools:
                self.add_rule(pattern, "allow", scope="session")
        if denied_tools:
            for pattern in denied_tools:
                self.add_rule(pattern, "deny", scope="session")
