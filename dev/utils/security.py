"""
Security hardening for Dev.

From Codex's security patterns.
Provides:
- Secret detection and masking
- Command sanitization
- Path traversal prevention
- Input validation
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional


# Patterns that look like secrets
SECRET_PATTERNS = [
    r'api[_-]?key\s*[=:]\s*["\']?([A-Za-z0-9_\-]{20,})["\']?',
    r'secret[_-]?key\s*[=:]\s*["\']?([A-Za-z0-9_\-]{20,})["\']?',
    r'token\s*[=:]\s*["\']?([A-Za-z0-9_\-]{20,})["\']?',
    r'password\s*[=:]\s*["\']?([^\s"\']{8,})["\']?',
    r'AWS_ACCESS_KEY_ID\s*[=:]\s*["\']?([A-Z0-9]{16,})["\']?',
    r'AWS_SECRET_ACCESS_KEY\s*[=:]\s*["\']?([A-Za-z0-9/+=]{40,})["\']?',
    r'ghp_[A-Za-z0-9]{36}',  # GitHub personal access token
    r'sk-[A-Za-z0-9]{32,}',   # OpenAI API key
    r'xoxb-[A-Za-z0-9\-]+',   # Slack bot token
]


class SecretDetector:
    """
    Detects and masks secrets in text.
    
    From Codex's secrets detection.
    """
    
    def __init__(self):
        self._patterns = [re.compile(p, re.IGNORECASE) for p in SECRET_PATTERNS]
    
    def detect(self, text: str) -> list[dict]:
        """Detect potential secrets in text."""
        findings = []
        
        for pattern in self._patterns:
            for match in pattern.finditer(text):
                findings.append({
                    "type": "secret",
                    "match": match.group()[:20] + "...",
                    "position": match.span(),
                })
        
        return findings
    
    def mask(self, text: str) -> str:
        """Mask potential secrets in text."""
        masked = text
        
        for pattern in self._patterns:
            masked = pattern.sub("[REDACTED]", masked)
        
        return masked
    
    def has_secrets(self, text: str) -> bool:
        """Check if text contains potential secrets."""
        return len(self.detect(text)) > 0


class CommandSanitizer:
    """
    Sanitize shell commands for safety.
    
    From Codex's command validation.
    """
    
    BLOCKED_PATTERNS = [
        r'rm\s+-rf\s+/',      # rm -rf /
        r'mkfs',              # format disk
        r'dd\s+if=',          # dd
        r'>\s*/dev/',         # write to device
        r'chmod\s+-R\s+777\s+/',  # chmod 777 /
        r'curl.*\|\s*sh',     # pipe to shell
        r'wget.*\|\s*sh',     # pipe to shell
        r'sudo\s+rm',         # sudo rm
        r'shutdown',          # shutdown
        r'reboot',            # reboot
    ]
    
    def __init__(self):
        self._blocked = [re.compile(p, re.IGNORECASE) for p in self.BLOCKED_PATTERNS]
    
    def is_safe(self, command: str) -> bool:
        """Check if a command is safe to run."""
        for pattern in self._blocked:
            if pattern.search(command):
                return False
        return True
    
    def sanitize(self, command: str) -> str:
        """Sanitize a command."""
        # Remove potentially dangerous characters
        command = command.replace('`', '')  # Backticks
        command = command.replace('$(', '')  # Command substitution
        return command
    
    def validate_path(self, path: str, project_root: str) -> bool:
        """Validate that a path is within the project root."""
        try:
            abs_path = os.path.abspath(os.path.join(project_root, path))
            abs_root = os.path.abspath(project_root)
            return abs_path.startswith(abs_root)
        except Exception:
            return False


class InputValidator:
    """
    Validate user input.
    
    From Codex's input validation.
    """
    
    MAX_PROMPT_LENGTH = 100_000
    MAX_FILE_PATH_LENGTH = 1000
    MAX_COMMAND_LENGTH = 10_000
    
    def validate_prompt(self, prompt: str) -> tuple[bool, str]:
        """Validate a prompt."""
        if not prompt or not prompt.strip():
            return False, "Prompt cannot be empty"
        
        if len(prompt) > self.MAX_PROMPT_LENGTH:
            return False, f"Prompt too long ({len(prompt)} chars, max {self.MAX_PROMPT_LENGTH})"
        
        return True, ""
    
    def validate_file_path(self, path: str) -> tuple[bool, str]:
        """Validate a file path."""
        if not path:
            return False, "Path cannot be empty"
        
        if len(path) > self.MAX_FILE_PATH_LENGTH:
            return False, "Path too long"
        
        # Check for path traversal
        if '..' in path:
            return False, "Path traversal not allowed"
        
        # Check for absolute paths outside project
        if os.path.isabs(path):
            return False, "Absolute paths not allowed"
        
        return True, ""
    
    def validate_command(self, command: str) -> tuple[bool, str]:
        """Validate a command."""
        if not command or not command.strip():
            return False, "Command cannot be empty"
        
        if len(command) > self.MAX_COMMAND_LENGTH:
            return False, "Command too long"
        
        sanitizer = CommandSanitizer()
        if not sanitizer.is_safe(command):
            return False, "Command contains blocked patterns"
        
        return True, ""


class SecurityAudit:
    """
    Audit project for security issues.
    
    From Codex's security scanning.
    """
    
    def audit_project(self, project_path: str) -> list[dict]:
        """Audit a project for security issues."""
        issues = []
        
        # Check for secrets in code
        detector = SecretDetector()
        
        for root, dirs, files in os.walk(project_path):
            # Skip common non-code dirs
            dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__pycache__', '.venv')]
            
            for filename in files:
                filepath = os.path.join(root, filename)
                
                # Only check text files
                if not self._is_text_file(filepath):
                    continue
                
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    findings = detector.detect(content)
                    for finding in findings:
                        issues.append({
                            "type": "secret",
                            "file": os.path.relpath(filepath, project_path),
                            "line": content[:finding["position"][0]].count('\n') + 1,
                            "detail": finding["match"],
                        })
                except Exception:
                    pass  # Intentional: non-critical: best-effort operation
        
        # Check for .gitignore
        gitignore_path = os.path.join(project_path, '.gitignore')
        if not os.path.exists(gitignore_path):
            issues.append({
                "type": "config",
                "detail": "No .gitignore file found",
            })
        
        # Check for .env files
        env_files = ['.env', '.env.local', '.env.production']
        for env_file in env_files:
            env_path = os.path.join(project_path, env_file)
            if os.path.exists(env_path):
                # Check if it's in .gitignore
                if os.path.exists(gitignore_path):
                    with open(gitignore_path) as f:
                        if env_file not in f.read():
                            issues.append({
                                "type": "security",
                                "file": env_file,
                                "detail": f"{env_file} not in .gitignore",
                            })
        
        return issues
    
    def _is_text_file(self, filepath: str) -> bool:
        """Check if a file is likely a text file."""
        text_extensions = {
            '.py', '.js', '.ts', '.tsx', '.jsx', '.rs', '.go', '.java',
            '.rb', '.php', '.html', '.css', '.json', '.yaml', '.yml',
            '.md', '.txt', '.sh', '.bash', '.zsh', '.env', '.config',
        }
        
        ext = Path(filepath).suffix.lower()
        return ext in text_extensions or not ext


class AuditLogger:
    """Audit logging for security-sensitive operations."""
    
    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
        self.audit_dir = os.path.join(self.project_path, ".dev", "audit")
        os.makedirs(self.audit_dir, exist_ok=True)
        self.audit_file = os.path.join(self.audit_dir, "audit.log")
    
    def log(self, action: str, details: dict, severity: str = "info"):
        """Log an audit event."""
        import time
        import json
        event = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "action": action,
            "severity": severity,
            **details,
        }
        try:
            with open(self.audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except Exception:
            pass  # Intentional: non-critical: best-effort operation
    
    def log_tool_use(self, tool_name: str, args: dict, result: dict):
        """Log a tool execution."""
        # Don't log read-only tool calls (too noisy)
        read_only = {"read_files", "code_search", "glob", "list_directory", "write_todos"}
        if tool_name in read_only:
            return
        self.log("tool_use", {
            "tool": tool_name,
            "args_summary": str(args)[:200],
            "success": "error" not in result,
        })
    
    def log_file_change(self, file_path: str, action: str):
        """Log a file modification."""
        self.log("file_change", {
            "path": file_path,
            "action": action,
        }, severity="warning")
    
    def log_security_event(self, event_type: str, details: dict):
        """Log a security event."""
        self.log("security", {
            "event_type": event_type,
            **details,
        }, severity="critical")
    
    def get_recent_logs(self, limit: int = 100) -> list[dict]:
        """Get recent audit log entries."""
        import json
        logs = []
        try:
            if os.path.isfile(self.audit_file):
                with open(self.audit_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                for line in lines[-limit:]:
                    try:
                        logs.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass  # Intentional: non-critical: best-effort operation
        return logs


class CredentialEncryptor:
    """
    Encrypt/decrypt API keys for storage.
    Uses machine-specific key derivation for local-only encryption.
    Not military-grade but prevents plain-text key storage.
    """

    def __init__(self):
        import hashlib, getpass, platform
        # Derive a machine-specific key from hostname + username
        seed = f"{platform.node()}-{getpass.getuser()}".encode()
        self._key = hashlib.sha256(seed).digest()[:32]

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string (XOR cipher with machine-derived key)."""
        import base64
        data = plaintext.encode('utf-8')
        key_bytes = self._key
        encrypted = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data))
        return base64.b64encode(encrypted).decode('ascii')

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a string encrypted with encrypt()."""
        import base64
        data = base64.b64decode(ciphertext)
        key_bytes = self._key
        decrypted = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data))
        return decrypted.decode('utf-8')

    def encrypt_config_keys(self, config_path: str) -> bool:
        """Encrypt API keys in a config file."""
        import json
        if not os.path.isfile(config_path):
            return False
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            keys = config.get('keys', [])
            if not keys:
                return True
            encrypted_keys = []
            for k in keys:
                if isinstance(k, str) and not k.startswith('enc:'):
                    encrypted_keys.append('enc:' + self.encrypt(k))
                else:
                    encrypted_keys.append(k)
            config['keys'] = encrypted_keys
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
            return True
        except Exception:
            return False

    def decrypt_config_keys(self, config_path: str) -> list[str]:
        """Decrypt API keys from a config file."""
        import json
        if not os.path.isfile(config_path):
            return []
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            keys = config.get('keys', [])
            decrypted = []
            for k in keys:
                if isinstance(k, str) and k.startswith('enc:'):
                    decrypted.append(self.decrypt(k[4:]))
                else:
                    decrypted.append(k)
            return decrypted
        except Exception:
            return []
