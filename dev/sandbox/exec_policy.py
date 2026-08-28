"""
Execution Policy system for Dev.

Adapted from Codex's execpolicy/src/:
- decision.rs - Allow/Prompt/Forbidden decisions
- rule.rs - Prefix-based command matching
- policy.rs - Policy evaluation engine

Controls which commands the agent can execute without user approval.
"""

from __future__ import annotations

import fnmatch
import os
import platform
import shlex
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Decision(str, Enum):
    """Decision for a command execution request."""
    ALLOW = "allow"       # Run without approval
    PROMPT = "prompt"     # Ask user for approval
    FORBIDDEN = "forbidden"  # Block entirely


class SandboxType(str, Enum):
    """Type of sandbox to use."""
    NONE = "none"
    PROCESS_ISOLATION = "process_isolation"  # Restricted subprocess
    DOCKER = "docker"                        # Docker container
    VIRTUALENV = "virtualenv"                # Python virtual environment


@dataclass
class RuleMatch:
    """Result of matching a command against rules."""
    decision: Decision
    matched_pattern: str
    command: str
    justification: str = ""


@dataclass
class CommandRule:
    """
    A rule for matching commands.
    
    From Codex's PrefixRule: matches command prefixes.
    """
    pattern: str  # Shell-style pattern (e.g., "git commit *")
    decision: Decision
    justification: str = ""
    
    def matches(self, command: str) -> bool:
        """Check if a command matches this rule's pattern."""
        # Normalize the command
        cmd_parts = shlex.split(command) if command else []
        pat_parts = shlex.split(self.pattern) if self.pattern else []
        
        if not pat_parts:
            return False
        
        # Check prefix match
        if len(cmd_parts) < len(pat_parts):
            return False
        
        for cmd_token, pat_token in zip(cmd_parts, pat_parts):
            # Support wildcards in pattern
            if '*' in pat_token or '?' in pat_token:
                if not fnmatch.fnmatch(cmd_token, pat_token):
                    return False
            elif cmd_token != pat_token:
                return False
        
        return True


@dataclass
class NetworkRule:
    """Rule for network access."""
    host_pattern: str  # e.g., "*.github.com", "api.openai.com"
    decision: Decision
    
    def matches(self, host: str) -> bool:
        return fnmatch.fnmatch(host, self.host_pattern)


@dataclass
class FileSystemRule:
    """Rule for file system access."""
    path_pattern: str  # e.g., "/tmp/*", "/home/user/project/**"
    read: bool = True
    write: bool = False
    
    def matches(self, path: str) -> bool:
        return fnmatch.fnmatch(path, self.path_pattern)


class ExecPolicy:
    """
    Execution policy engine.
    
    Adapted from Codex's Policy struct:
    - Rules indexed by command prefix
    - Evaluate commands against rules
    - Fall back to default decision
    """
    
    def __init__(self):
        self._command_rules: list[CommandRule] = []
        self._network_rules: list[NetworkRule] = []
        self._filesystem_rules: list[FileSystemRule] = []
        self._default_decision = Decision.PROMPT
        self._approval_mode = "auto"  # "auto", "always", "never"
    
    def set_approval_mode(self, mode: str):
        """
        Set approval mode.
        
        From Codex's approval_policy:
        - "auto": Use rules to decide
        - "always": Always prompt
        - "never": Never prompt (allow or forbidden only)
        """
        self._approval_mode = mode
    
    def add_command_rule(self, rule: CommandRule):
        """Add a command execution rule."""
        self._command_rules.append(rule)
    
    def add_network_rule(self, rule: NetworkRule):
        """Add a network access rule."""
        self._network_rules.append(rule)
    
    def add_filesystem_rule(self, rule: FileSystemRule):
        """Add a filesystem access rule."""
        self._filesystem_rules.append(rule)
    
    def evaluate_command(self, command: str) -> RuleMatch:
        """
        Evaluate a command against the policy.
        
        Returns a RuleMatch with the decision.
        """
        # Check approval mode
        if self._approval_mode == "always":
            return RuleMatch(
                decision=Decision.PROMPT,
                matched_pattern="*",
                command=command,
                justification="Approval mode is 'always'",
            )
        
        # Check against rules (first match wins)
        for rule in self._command_rules:
            if rule.matches(command):
                return RuleMatch(
                    decision=rule.decision,
                    matched_pattern=rule.pattern,
                    command=command,
                    justification=rule.justification,
                )
        
        # No rule matched - use default
        return RuleMatch(
            decision=self._default_decision,
            matched_pattern="*",
            command=command,
            justification="No matching rule",
        )
    
    def evaluate_network(self, host: str) -> Decision:
        """Evaluate network access to a host."""
        for rule in self._network_rules:
            if rule.matches(host):
                return rule.decision
        return self._default_decision
    
    def evaluate_filesystem(self, path: str, write: bool = False) -> Decision:
        """Evaluate filesystem access."""
        for rule in self._filesystem_rules:
            if rule.matches(path):
                if write and not rule.write:
                    return Decision.FORBIDDEN
                return Decision.ALLOW
        return self._default_decision


def create_default_policy(project_path: str = ".") -> ExecPolicy:
    """
    Create a default execution policy.
    
    Based on Codex's default permission profiles:
    - Read anywhere: ALLOW
    - Write to project: ALLOW
    - Write outside project: PROMPT
    - Dangerous commands: FORBIDDEN
    - Safe commands: ALLOW
    """
    policy = ExecPolicy()
    
    # === COMMAND RULES ===
    
    # Always allowed - read-only commands
    safe_commands = [
        "ls", "dir", "pwd", "echo", "cat", "head", "tail", "wc",
        "grep", "find", "which", "whoami", "date", "env",
        "git status", "git log", "git diff", "git show", "git branch",
        "git remote", "git tag",
        "python --version", "python3 --version", "node --version",
        "npm --version", "pip list", "pip show",
        "cargo --version", "rustc --version",
        "go version",
    ]
    
    for cmd in safe_commands:
        policy.add_command_rule(CommandRule(
            pattern=cmd,
            decision=Decision.ALLOW,
            justification="Safe read-only command",
        ))
    
    # Allowed with project context
    project_commands = [
        "git add", "git commit", "git push", "git pull", "git checkout",
        "git merge", "git rebase",
        "npm install", "npm run", "npm test", "npm build",
        "yarn install", "yarn run", "yarn test",
        "pip install", "pip uninstall",
        "cargo build", "cargo test", "cargo run",
        "go build", "go test", "go run",
        "make", "cmake",
        "docker build", "docker run", "docker-compose",
    ]
    
    for cmd in project_commands:
        policy.add_command_rule(CommandRule(
            pattern=cmd,
            decision=Decision.PROMPT,
            justification="Project command - needs approval",
        ))
    
    # Always forbidden - dangerous commands
    dangerous_commands = [
        "rm -rf /",
        "rm -rf ~",
        "mkfs",
        "dd if=",
        "> /dev/",
        "chmod -R 777 /",
        "wget * | sh",
        "curl * | sh",
        "sudo rm",
        "shutdown",
        "reboot",
        "init 0",
        "kill -9 1",
        "killall",
    ]
    
    for cmd in dangerous_commands:
        policy.add_command_rule(CommandRule(
            pattern=cmd,
            decision=Decision.FORBIDDEN,
            justification="Dangerous command - blocked",
        ))
    
    # === FILESYSTEM RULES ===
    
    # Allow reading everywhere
    policy.add_filesystem_rule(FileSystemRule(
        path_pattern="*",
        read=True,
        write=False,
    ))
    
    # Allow writing to project
    abs_project = os.path.abspath(project_path)
    policy.add_filesystem_rule(FileSystemRule(
        path_pattern=f"{abs_project}/**",
        read=True,
        write=True,
    ))
    
    # Allow writing to temp
    policy.add_filesystem_rule(FileSystemRule(
        path_pattern="/tmp/*",
        read=True,
        write=True,
    ))
    
    # Allow writing to home
    home = os.path.expanduser("~")
    policy.add_filesystem_rule(FileSystemRule(
        path_pattern=f"{home}/.dev/**",
        read=True,
        write=True,
    ))
    
    # === NETWORK RULES ===
    
    # Allow common dev hosts
    allowed_hosts = [
        "*.github.com",
        "*.gitlab.com",
        "*.npmjs.org",
        "*.npmjs.com",
        "*.pypi.org",
        "*.crates.io",
        "*.nuget.org",
        "registry.npmjs.org",
        "pypi.org",
        "docs.python.org",
        "*.stackoverflow.com",
        "integrate.api.nvidia.com",  # NVIDIA NIMs
        "openrouter.ai",         # OpenRouter
        "api.openrouter.ai",
        "*.openrouter.ai",
        "*.bytez.com",            # Bytez
        "*.googleapis.com",       # Google APIs
        "*.openai.com",           # OpenAI-compatible APIs
        "raw.githubusercontent.com",
        "api.github.com",
        "*.cloudflare.com",
        "fonts.googleapis.com",
        "*.tailwindcss.com",
        "registry.npmjs.org",
    ]
    
    for host in allowed_hosts:
        policy.add_network_rule(NetworkRule(
            host_pattern=host,
            decision=Decision.ALLOW,
        ))
    
    return policy


def create_strict_policy(project_path: str = ".") -> ExecPolicy:
    """
    Create a strict policy that requires approval for everything.
    
    Use this for untrusted code or new projects.
    """
    policy = ExecPolicy()
    policy.set_approval_mode("always")
    
    # Only allow truly safe commands
    safe_commands = ["ls", "pwd", "echo", "cat", "git status", "git log"]
    for cmd in safe_commands:
        policy.add_command_rule(CommandRule(
            pattern=cmd,
            decision=Decision.ALLOW,
            justification="Strict mode - only safe commands allowed",
        ))
    
    # Everything else needs approval
    policy._default_decision = Decision.PROMPT
    
    return policy


def create_permissive_policy(project_path: str = ".") -> ExecPolicy:
    """
    Create a permissive policy that allows most commands.
    
    Use this for trusted local development.
    """
    policy = ExecPolicy()
    
    # Allow most commands
    policy._default_decision = Decision.ALLOW
    
    # Still block truly dangerous ones
    dangerous = ["rm -rf /", "mkfs", "dd if=", "> /dev/"]
    for cmd in dangerous:
        policy.add_command_rule(CommandRule(
            pattern=cmd,
            decision=Decision.FORBIDDEN,
            justification="Always blocked",
        ))
    
    return policy
