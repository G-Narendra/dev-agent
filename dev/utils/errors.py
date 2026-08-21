"""
Error handling system for Dev.

Provides:
- Custom exception hierarchy
- Error recovery strategies
- User-friendly error messages
- Debug logging
"""

from __future__ import annotations

import os
import sys
import traceback
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class ErrorSeverity(str, Enum):
    """Error severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class DevError(Exception):
    """Base exception for Dev."""
    
    def __init__(self, message: str, severity: ErrorSeverity = ErrorSeverity.ERROR):
        super().__init__(message)
        self.severity = severity
        self.message = message
    
    def to_dict(self) -> dict:
        return {
            "error": type(self).__name__,
            "message": self.message,
            "severity": self.severity.value,
        }


class ProviderError(DevError):
    """Error with LLM provider."""
    pass


class ToolError(DevError):
    """Error in tool execution."""
    pass


class SandboxError(DevError):
    """Error with sandbox."""
    pass


class ConfigError(DevError):
    """Configuration error."""
    pass


class TokenLimitError(DevError):
    """Token limit exceeded."""
    
    def __init__(self, used: int, limit: int):
        super().__init__(
            f"Token limit exceeded: {used:,} / {limit:,}",
            ErrorSeverity.WARNING,
        )
        self.used = used
        self.limit = limit


class RateLimitError(DevError):
    """Rate limit exceeded."""
    
    def __init__(self, retry_after: float = 60.0):
        super().__init__(
            f"Rate limit exceeded. Retry after {retry_after:.0f}s",
            ErrorSeverity.WARNING,
        )
        self.retry_after = retry_after


class ToolExecutionError(DevError):
    """Error executing a tool."""
    
    def __init__(self, tool_name: str, message: str, details: dict | None = None):
        super().__init__(
            f"Tool '{tool_name}' failed: {message}",
            ErrorSeverity.ERROR,
        )
        self.tool_name = tool_name
        self.details = details or {}
    
    def to_dict(self) -> dict:
        result = super().to_dict()
        result["tool"] = self.tool_name
        result["details"] = self.details
        return result


@dataclass
class ErrorContext:
    """Context information for an error."""
    operation: str = ""
    file_path: str = ""
    tool_name: str = ""
    attempt: int = 0
    max_attempts: int = 1
    additional_info: dict = None
    
    def __post_init__(self):
        if self.additional_info is None:
            self.additional_info = {}


class ErrorHandler:
    """
    Centralized error handler.
    
    Provides:
    - Error classification
    - Recovery strategies
    - User-friendly messages
    - Debug logging
    """
    
    def __init__(self, verbose: bool = False, log_file: str | None = None):
        self.verbose = verbose
        self.log_file = log_file
        self._error_count = 0
        self._errors: list[dict] = []
    
    def handle(self, error: Exception, context: ErrorContext | None = None) -> dict:
        """
        Handle an error and return a user-friendly response.
        
        Returns:
            dict with keys: message, severity, recoverable, details
        """
        self._error_count += 1
        
        error_info = {
            "type": type(error).__name__,
            "message": str(error),
            "severity": ErrorSeverity.ERROR.value,
            "recoverable": False,
            "details": {},
        }
        
        # Classify error
        if isinstance(error, ProviderError):
            error_info["severity"] = ErrorSeverity.WARNING.value
            error_info["recoverable"] = True
            error_info["message"] = self._format_provider_error(error)
        
        elif isinstance(error, TokenLimitError):
            error_info["severity"] = ErrorSeverity.WARNING.value
            error_info["recoverable"] = True
            error_info["message"] = self._format_token_error(error)
        
        elif isinstance(error, RateLimitError):
            error_info["severity"] = ErrorSeverity.WARNING.value
            error_info["recoverable"] = True
            error_info["retry_after"] = error.retry_after
            error_info["message"] = f"Rate limited. Retry in {error.retry_after:.0f}s"
        
        elif isinstance(error, ToolExecutionError):
            error_info["severity"] = ErrorSeverity.ERROR.value
            error_info["recoverable"] = True
            error_info["tool"] = error.tool_name
            error_info["details"] = error.details
            error_info["message"] = f"Tool '{error.tool_name}' failed: {error.message}"
        
        elif isinstance(error, SandboxError):
            error_info["severity"] = ErrorSeverity.WARNING.value
            error_info["recoverable"] = False
            error_info["message"] = f"Sandbox error: {error.message}"
        
        elif isinstance(error, FileNotFoundError):
            error_info["severity"] = ErrorSeverity.ERROR.value
            error_info["recoverable"] = False
            error_info["message"] = f"File not found: {error}"
        
        elif isinstance(error, PermissionError):
            error_info["severity"] = ErrorSeverity.ERROR.value
            error_info["recoverable"] = False
            error_info["message"] = f"Permission denied: {error}"
        
        elif isinstance(error, ConnectionError):
            error_info["severity"] = ErrorSeverity.WARNING.value
            error_info["recoverable"] = True
            error_info["message"] = "Connection error. Check your network."
        
        elif isinstance(error, TimeoutError):
            error_info["severity"] = ErrorSeverity.WARNING.value
            error_info["recoverable"] = True
            error_info["message"] = "Operation timed out"
        
        else:
            # Unknown error
            error_info["message"] = f"Unexpected error: {error}"
            if self.verbose:
                error_info["traceback"] = traceback.format_exc()
        
        # Add context
        if context:
            error_info["context"] = {
                "operation": context.operation,
                "file_path": context.file_path,
                "tool_name": context.tool_name,
                "attempt": context.attempt,
            }
        
        # Log error
        self._log_error(error_info)
        
        # Store for later
        self._errors.append(error_info)
        
        return error_info
    
    def _format_provider_error(self, error: ProviderError) -> str:
        """Format provider error for user."""
        msg = str(error).lower()
        
        if "rate" in msg or "429" in msg:
            return "Rate limited by provider. Waiting before retry..."
        elif "timeout" in msg:
            return "Provider timed out. The model may be overloaded."
        elif "502" in msg or "503" in msg:
            return "Provider temporarily unavailable. Retrying..."
        elif "auth" in msg or "401" in msg or "403" in msg:
            return "Authentication failed. Check your API key."
        elif "quota" in msg:
            return "API quota exceeded."
        else:
            return f"Provider error: {error.message}"
    
    def _format_token_error(self, error: TokenLimitError) -> str:
        """Format token limit error for user."""
        return (
            f"Context too large ({error.used:,} tokens). "
            f"Limit is {error.limit:,} tokens. "
            f"Try: /clear to reset, or break into smaller tasks."
        )
    
    def _log_error(self, error_info: dict):
        """Log error to file if configured."""
        if not self.log_file:
            return
        
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(error_info) + "\n")
        except Exception:
            pass
    
    def get_stats(self) -> dict:
        """Get error statistics."""
        return {
            "total_errors": self._error_count,
            "recent_errors": self._errors[-10:],
            "error_types": {},
        }
    
    def clear(self):
        """Clear error history."""
        self._error_count = 0
        self._errors.clear()
