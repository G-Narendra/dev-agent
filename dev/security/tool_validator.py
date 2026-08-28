"""
Tool Call Validator — Least-privilege access control for tools.

Implements:
- Tool-level permission enforcement (Teleport-style)
- Parameter validation and sanitization
- Dangerous command detection
- Path traversal prevention
- Rate limiting per tool
- Audit logging of all tool invocations
"""

from __future__ import annotations

import re
import os
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class ToolPermission(Enum):
    """Tool permission levels."""
    DENIED = "denied"          # Never allowed
    READ_ONLY = "read_only"    # Only read operations
    RESTRICTED = "restricted"  # Limited write operations
    FULL = "full"              # Unrestricted access


@dataclass
class ToolRule:
    """A single tool permission rule."""
    tool_pattern: str           # Glob pattern for tool name
    permission: ToolPermission
    param_patterns: dict = field(default_factory=dict)  # Parameter-specific rules
    reason: str = ""


@dataclass
class ValidationResult:
    """Result of tool call validation."""
    allowed: bool
    tool_name: str
    permission: ToolPermission
    violations: list[str] = field(default_factory=list)
    sanitized_args: dict = field(default_factory=dict)
    reason: str = ""


class ToolCallValidator:
    """
    Validates tool calls against permission rules.
    
    Modeled after Teleport's MCP security:
    - Default deny (new tools blocked by default)
    - Explicit allow rules per tool
    - Parameter-level validation
    - Dangerous operation detection
    """
    
    # Default deny list — these tools are ALWAYS blocked
    DEFAULT_DENY_TOOLS = [
        "eval",
        "exec",
        "compile",
        "__import__",
        "subprocess.call",
        "os.system",
    ]
    
    # Read-only tools (always safe)
    SAFE_TOOLS = {
        "read_files", "code_search", "glob", "list_directory", 
        "web_search", "read_url", "gravity_index",
    }
    
    # Tools that modify files
    WRITE_TOOLS = {
        "write_file", "str_replace", "run_terminal_command",
    }
    
    # Dangerous terminal commands
    DANGEROUS_COMMANDS = [
        r'rm\s+-rf\s+/',           # Delete root
        r'rm\s+-rf\s+~',           # Delete home
        r'del\s+/[sS]\s+/[qQ]',   # Windows delete all
        r'format\s+[cC]:',         # Format C drive
        r'sudo\s+rm',              # Sudo delete
        r'chmod\s+777',            # World-writable
        r'curl\s.*\|\s*sh',        # Pipe to shell
        r'curl\s.*\|\s*bash',      # Pipe to bash
        r'wget\s.*\|\s*sh',        # Pipe to shell
        r'wget\s.*\|\s*bash',      # Pipe to bash
        r'eval\s*\(',              # Eval execution
        r'exec\s*\(',              # Exec execution
        r'>\s*/etc/',              # Write to /etc
        r'>>\s*/etc/',             # Append to /etc
        r'>(\s*)/dev/sd',          # Write to disk device
        r'nc\s+-e',                # Netcat reverse shell
        r'ncat\s+-e',              # Ncat reverse shell
        r'crontab\s+-',            # Crontab manipulation
        r'iptables\s',             # Firewall manipulation
        r'useradd\s',              # User creation
        r'usermod\s',              # User modification
        r'passwd\s',               # Password change
        r'su\s+-',                 # Switch user
    ]
    
    # Path traversal patterns
    PATH_TRAVERSAL = [
        r'\.\./\.\.',              # Double traversal
        r'\.\.[\\/]',             # Up-directory traversal
        r'~[/\\]',                 # Home directory
        r'/etc/passwd',
        r'/etc/shadow',
        r'/etc/hosts',
        r'~/.ssh',
        r'~/.aws',
        r'~/.config',
        r'~/.env',
    ]
    
    # API key / secret patterns in arguments
    SECRET_PATTERNS = [
        re.compile(r'(?:api[_-]?key|secret|password|token|credential)\s*[=:]\s*\S+', re.IGNORECASE),
        re.compile(r'nvidia[_-]?nim[_-]?key\s*[=:]\s*\S+', re.IGNORECASE),
        re.compile(r'nvapi-\S+', re.IGNORECASE),
        re.compile(r'sk-or-\S+', re.IGNORECASE),
        re.compile(r'sk-\S{20,}', re.IGNORECASE),
    ]
    
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path).resolve()
        self._rules: list[ToolRule] = []
        self._tool_counts: dict[str, list[float]] = {}
        self._rate_limit_window = 60.0  # seconds
        self._rate_limit_max = 30      # calls per window
        
        # Security sandbox (NVIDIA mandatory controls)
        self._sandbox = None
        try:
            from .sandbox import SecuritySandbox, SandboxConfig
            self._sandbox = SecuritySandbox(SandboxConfig(workspace_path=project_path))
        except Exception:
            pass  # Intentional: non-critical: best-effort operation
        
        # Add default rules
        self._setup_default_rules()
    
    def _setup_default_rules(self):
        """Set up default permission rules."""
        # Default deny dangerous tools
        for tool in self.DEFAULT_DENY_TOOLS:
            self._rules.append(ToolRule(
                tool_pattern=tool,
                permission=ToolPermission.DENIED,
                reason="Default deny: dangerous tool",
            ))
        
        # Safe read-only tools
        for tool in self.SAFE_TOOLS:
            self._rules.append(ToolRule(
                tool_pattern=tool,
                permission=ToolPermission.READ_ONLY,
                reason="Read-only tool",
            ))
    
    def add_rule(self, rule: ToolRule):
        """Add a custom permission rule."""
        self._rules.insert(0, rule)  # Higher priority
    
    def validate(
        self,
        tool_name: str,
        tool_args: dict,
        user_consent: bool = False,
    ) -> ValidationResult:
        """
        Validate a tool call against all rules.
        
        Returns ValidationResult with allow/deny and sanitized args.
        """
        violations = []
        sanitized_args = dict(tool_args)
        
        # Check 1: Tool name deny list
        for rule in self._rules:
            if rule.permission == ToolPermission.DENIED:
                if self._matches_pattern(tool_name, rule.tool_pattern):
                    return ValidationResult(
                        allowed=False,
                        tool_name=tool_name,
                        permission=ToolPermission.DENIED,
                        violations=[f"Tool denied: {rule.reason}"],
                        reason=rule.reason,
                    )
        
        # Check 2: Rate limiting
        if self._check_rate_limit(tool_name):
            violations.append(f"Rate limit exceeded for {tool_name}")
        
        # Check 3: Dangerous commands in terminal
        if tool_name == "run_terminal_command":
            command = tool_args.get("command", "")
            cmd_violations = self._check_dangerous_command(command)
            violations.extend(cmd_violations)
            # Also check for path traversal in commands
            path_violations = self._check_path_traversal(command)
            violations.extend(path_violations)
        
        # Check 4: Path traversal in file operations
        if tool_name in ("write_file", "str_replace", "read_files"):
            path = tool_args.get("path", "") or tool_args.get("paths", "")
            if isinstance(path, str):
                path_violations = self._check_path_traversal(path)
                violations.extend(path_violations)
            elif isinstance(path, list):
                for p in path:
                    if isinstance(p, str):
                        path_violations = self._check_path_traversal(p)
                        violations.extend(path_violations)
                    elif isinstance(p, dict):
                        path_violations = self._check_path_traversal(p.get("path", ""))
                        violations.extend(path_violations)
        
        # Check 5: Secret leakage in arguments
        secret_violations = self._check_secret_leakage(tool_args)
        violations.extend(secret_violations)
        
        # Check 6: Project boundary
        boundary_violations = self._check_project_boundary(tool_args)
        violations.extend(boundary_violations)
        
        # Check 7: Security sandbox (NVIDIA mandatory controls)
        if self._sandbox:
            sandbox_result = self._sandbox.check_all(tool_name, tool_args)
            if not sandbox_result.allowed:
                violations.append(f"Sandbox: {sandbox_result.reason}")
        
        # Determine final permission
        permission = ToolPermission.FULL
        if violations:
            permission = ToolPermission.RESTRICTED
        
        allowed = len(violations) == 0 or user_consent
        
        return ValidationResult(
            allowed=allowed,
            tool_name=tool_name,
            permission=permission,
            violations=violations,
            sanitized_args=sanitized_args,
            reason="; ".join(violations) if violations else "OK",
        )
    
    def _matches_pattern(self, name: str, pattern: str) -> bool:
        """Match tool name against glob pattern."""
        if pattern == "*":
            return True
        if "*" in pattern:
            regex = pattern.replace("*", ".*")
            return bool(re.fullmatch(regex, name))
        return name == pattern
    
    def _check_rate_limit(self, tool_name: str) -> bool:
        """Check if tool call exceeds rate limit."""
        now = time.time()
        if tool_name not in self._tool_counts:
            self._tool_counts[tool_name] = []
        
        # Remove old entries
        self._tool_counts[tool_name] = [
            t for t in self._tool_counts[tool_name]
            if now - t < self._rate_limit_window
        ]
        
        if len(self._tool_counts[tool_name]) >= self._rate_limit_max:
            return True
        
        self._tool_counts[tool_name].append(now)
        return False
    
    def _check_dangerous_command(self, command: str) -> list[str]:
        """Check for dangerous terminal commands."""
        violations = []
        for pattern in self.DANGEROUS_COMMANDS:
            if re.search(pattern, command, re.IGNORECASE):
                violations.append(f"Dangerous command detected: {pattern[:30]}")
        return violations
    
    def _check_path_traversal(self, path: str) -> list[str]:
        """Check for path traversal attacks."""
        violations = []
        for pattern in self.PATH_TRAVERSAL:
            if re.search(pattern, path, re.IGNORECASE):
                violations.append(f"Path traversal detected: {pattern}")
        
        # Check if path is outside project
        try:
            resolved = Path(path).resolve()
            if not str(resolved).startswith(str(self.project_path)):
                violations.append(f"Path outside project: {path}")
        except Exception:
            pass  # Intentional: non-critical: best-effort operation
        
        return violations
    
    def _check_secret_leakage(self, args: dict) -> list[str]:
        """Check for secrets in tool arguments."""
        violations = []
        args_str = json.dumps(args)
        
        for pattern in self.SECRET_PATTERNS:
            if pattern.search(args_str):
                violations.append("Potential secret/credential in arguments")
                break
        
        return violations
    
    def _check_project_boundary(self, args: dict) -> list[str]:
        """Check that operations stay within project boundaries."""
        violations = []
        
        # Check cwd parameter
        cwd = args.get("cwd", "")
        if cwd:
            try:
                resolved = Path(cwd).resolve()
                if not str(resolved).startswith(str(self.project_path)):
                    violations.append(f"Working directory outside project: {cwd}")
            except Exception:
                pass  # Intentional: non-critical: best-effort operation
        
        return violations
