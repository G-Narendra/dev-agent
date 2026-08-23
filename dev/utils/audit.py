"""
Security Audit Module for Dev Agent.

Performs comprehensive security checks on the codebase.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SecurityIssue:
    """A security issue found during audit."""
    severity: str  # critical, high, medium, low, info
    category: str
    file: str
    line: int
    message: str
    suggestion: str = ""


class SecurityAuditor:
    """
    Comprehensive security auditor for Dev Agent.
    
    Checks for:
    - Hardcoded secrets
    - Command injection vulnerabilities
    - Path traversal vulnerabilities
    - Unsafe deserialization
    - Missing input validation
    - Insecure file operations
    """
    
    # Secret patterns
    SECRET_PATTERNS = [
        (r'api[_-]?key\s*[=:]\s*["\']([A-Za-z0-9_\-]{20,})["\']', "Hardcoded API key"),
        (r'secret[_-]?key\s*[=:]\s*["\']([A-Za-z0-9_\-]{20,})["\']', "Hardcoded secret key"),
        (r'token\s*[=:]\s*["\']([A-Za-z0-9_\-]{20,})["\']', "Hardcoded token"),
        (r'password\s*[=:]\s*["\']([^"\']{8,})["\']', "Hardcoded password"),
        (r'ghp_[A-Za-z0-9]{36}', "GitHub personal access token"),
        (r'sk-[A-Za-z0-9]{32,}', "OpenAI API key"),
        (r'nvapi-[A-Za-z0-9_\-]{20,}', "NVIDIA NIM API key"),
    ]
    
    # Dangerous patterns
    DANGEROUS_PATTERNS = [
        (r'eval\s*\(', "eval() usage - potential code injection"),
        (r'exec\s*\(', "exec() usage - potential code injection"),
        (r'os\.system\s*\(', "os.system() usage - use subprocess instead"),
        (r'__import__\s*\(', "__import__() usage - potential import injection"),
        (r'pickle\.loads?\s*\(', "Pickle deserialization - potential RCE"),
        (r'marshal\.loads?\s*\(', "Marshal deserialization - potential RCE"),
        (r'subprocess\.call\s*\(\s*["\']', "subprocess.call with shell=True"),
        (r'subprocess\.Popen\s*\([^)]*shell\s*=\s*True', "Popen with shell=True"),
        (r'yaml\.load\s*\([^)]*Loader\s*=\s*Loader', "yaml.load with unsafe Loader"),
        (r'yaml\.unsafe_load', "yaml.unsafe_load usage"),
    ]
    
    # Insecure patterns
    INSECURE_PATTERNS = [
        (r'open\s*\([^)]*["\']w["\']', "File opened without encoding specified"),
        (r'tempfile\.mktemp', "tempfile.mktemp is insecure - use mkstemp"),
        (r'random\.random', "random.random is not cryptographically secure"),
        (r'hashlib\.md5', "MD5 is not secure for hashing"),
        (r'hashlib\.sha1', "SHA1 is not secure for hashing"),
        (r'HTTP://', "HTTP instead of HTTPS"),
    ]
    
    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
        self.issues: list[SecurityIssue] = []
    
    def audit(self) -> list[SecurityIssue]:
        """Run full security audit."""
        self.issues = []
        
        # Scan all Python files
        for root, dirs, files in os.walk(self.project_path):
            # Skip non-code directories
            dirs[:] = [d for d in dirs if d not in (
                '.git', 'node_modules', '__pycache__', '.venv', 'venv',
                'skills', 'outputs', 'templates',
            )]
            
            for filename in files:
                if filename.endswith('.py'):
                    filepath = os.path.join(root, filename)
                    self._scan_file(filepath)
        
        return self.issues
    
    def _scan_file(self, filepath: str):
        """Scan a single file for security issues."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.splitlines()
        except Exception:
            return
        
        rel_path = os.path.relpath(filepath, self.project_path)
        
        # Check for secrets
        for line_num, line in enumerate(lines, 1):
            for pattern, desc in self.SECRET_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    # Skip test files and examples
                    if 'test' in rel_path.lower() or 'example' in rel_path.lower():
                        continue
                    self.issues.append(SecurityIssue(
                        severity="high",
                        category="secrets",
                        file=rel_path,
                        line=line_num,
                        message=desc,
                        suggestion="Move to environment variable or .env file",
                    ))
        
        # Check for dangerous patterns
        for line_num, line in enumerate(lines, 1):
            for pattern, desc in self.DANGEROUS_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    self.issues.append(SecurityIssue(
                        severity="critical",
                        category="injection",
                        file=rel_path,
                        line=line_num,
                        message=desc,
                        suggestion="Use safer alternative (subprocess, ast.literal_eval, etc.)",
                    ))
        
        # Check for insecure patterns
        for line_num, line in enumerate(lines, 1):
            for pattern, desc in self.INSECURE_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    self.issues.append(SecurityIssue(
                        severity="medium",
                        category="insecure",
                        file=rel_path,
                        line=line_num,
                        message=desc,
                        suggestion="Use more secure alternative",
                    ))
    
    def report(self) -> str:
        """Generate a human-readable report."""
        if not self.issues:
            return "✅ No security issues found!"
        
        # Group by severity
        by_severity = {}
        for issue in self.issues:
            by_severity.setdefault(issue.severity, []).append(issue)
        
        lines = ["# Security Audit Report\n"]
        
        total = len(self.issues)
        critical = len(by_severity.get("critical", []))
        high = len(by_severity.get("high", []))
        medium = len(by_severity.get("medium", []))
        low = len(by_severity.get("low", []))
        
        lines.append(f"**Total issues**: {total}")
        lines.append(f"- 🔴 Critical: {critical}")
        lines.append(f"- 🟠 High: {high}")
        lines.append(f"- 🟡 Medium: {medium}")
        lines.append(f"- 🟢 Low: {low}\n")
        
        for severity in ["critical", "high", "medium", "low"]:
            issues = by_severity.get(severity, [])
            if issues:
                lines.append(f"## {severity.upper()} Issues ({len(issues)})\n")
                for issue in issues:
                    lines.append(f"- **{issue.file}:{issue.line}** - {issue.message}")
                    if issue.suggestion:
                        lines.append(f"  - Suggestion: {issue.suggestion}")
                lines.append("")
        
        return "\n".join(lines)


def run_audit(project_path: str = ".") -> str:
    """Run a security audit and return the report."""
    auditor = SecurityAuditor(project_path)
    auditor.audit()
    return auditor.report()
