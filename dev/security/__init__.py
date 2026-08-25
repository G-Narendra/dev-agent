"""
Dev Agent Security Module — Teleport-style + OWASP defenses.

Implements:
- Prompt injection detection and defense (OWASP LLM Top 10)
- Tool call validation and parameter sanitization
- Least-privilege access control for MCP/APIs
- Output monitoring for sensitive data leakage
- Human-in-the-loop controls
- Audit logging for all actions
"""

from .injection_detector import PromptInjectionDetector
from .tool_validator import ToolCallValidator
from .audit_logger import AuditLogger
from .output_monitor import OutputMonitor

__all__ = [
    "PromptInjectionDetector",
    "ToolCallValidator",
    "AuditLogger",
    "OutputMonitor",
]
