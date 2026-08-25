"""
Output Monitor — Detects sensitive data leakage in LLM responses.

Monitors:
- API keys and tokens in output
- File paths that shouldn't be exposed
- System prompt leakage
- PII (emails, phone numbers, SSNs)
- Credentials and passwords
- Internal infrastructure details

Reference: OWASP LLM06 — Sensitive Information Disclosure
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class MonitorResult:
    """Result of output monitoring."""
    safe: bool
    violations: list[str]
    sanitized_output: str
    original_length: int
    sanitized_length: int


class OutputMonitor:
    """
    Monitors LLM output for sensitive data leakage.
    
    Catches:
    1. API keys and tokens
    2. System prompt fragments
    3. PII (emails, phones, SSNs)
    4. Infrastructure details (internal IPs, hostnames)
    5. Credential patterns
    """
    
    # Patterns that should NEVER appear in output
    SENSITIVE_PATTERNS = [
        # API keys and tokens
        (re.compile(r'(?:nvapi|sk-or|sk-ant|sk-proj|ghp|gho|npm_|AKIA)\S{10,}', re.IGNORECASE), "API key/token"),
        
        # System prompt leakage
        (re.compile(r'You are (?:a |an )?(?:AI |LLM |language model|coding assistant).*?(?:\n|$)', re.IGNORECASE), "System prompt fragment"),
        (re.compile(r'SYSTEM_INSTRUCTIONS?:.*?(?:\n\n|$)', re.IGNORECASE | re.DOTALL), "System instructions leak"),
        
        # PII patterns
        (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), "Email address"),
        (re.compile(r'\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b'), "Phone number"),
        (re.compile(r'\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b'), "SSN pattern"),
        
        # Password/credential patterns
        (re.compile(r'(?:password|passwd|pwd)\s*[=:]\s*\S+', re.IGNORECASE), "Password"),
        (re.compile(r'(?:api[_-]?key|secret[_-]?key|access[_-]?key)\s*[=:]\s*\S+', re.IGNORECASE), "Secret key"),
        
        # Infrastructure
        (re.compile(r'\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})\b'), "Internal IP address"),
        
        # Private keys
        (re.compile(r'-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----'), "Private key"),
        
        # JWT tokens
        (re.compile(r'eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+'), "JWT token"),
    ]
    
    def __init__(self, strict_mode: bool = False):
        self.strict_mode = strict_mode
    
    def check(self, output: str) -> MonitorResult:
        """
        Check LLM output for sensitive data leakage.
        
        Returns MonitorResult with sanitized output.
        """
        violations = []
        sanitized = output
        
        for pattern, description in self.SENSITIVE_PATTERNS:
            matches = pattern.findall(sanitized)
            if matches:
                violations.append(f"{description}: {len(matches)} occurrence(s)")
                # Redact the matches
                sanitized = pattern.sub(f'[REDACTED:{description.upper()}]', sanitized)
        
        # Check for system prompt boundaries
        if 'SYSTEM_INSTRUCTIONS:' in output or 'SYSTEM_PROMPT:' in output:
            violations.append("System prompt boundary detected")
        
        safe = len(violations) == 0
        
        return MonitorResult(
            safe=safe,
            violations=violations,
            sanitized_output=sanitized,
            original_length=len(output),
            sanitized_length=len(sanitized),
        )
    
    def check_tool_result(self, result: str, tool_name: str = "") -> MonitorResult:
        """Check tool results for sensitive data before adding to context."""
        return self.check(result)
