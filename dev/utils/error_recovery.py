"""
Error Recovery for Dev.

Handles tool execution failures with retry, fallback, and recovery strategies.
"""

from __future__ import annotations

import asyncio
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class RetryConfig:
    """Configuration for retry logic."""
    max_retries: int = 3
    base_delay: float = 0.5
    max_delay: float = 30.0
    exponential_base: float = 2.0


class ToolRetry:
    """Retry logic for tool execution."""
    
    def __init__(self, config: RetryConfig | None = None):
        self.config = config or RetryConfig()
        self._stats: dict[str, int] = {"retries": 0, "successes": 0, "failures": 0}
    
    def is_retryable(self, error: Exception) -> bool:
        """Check if an error is retryable."""
        error_str = str(error).lower()
        retryable_patterns = [
            "timeout", "timed out", "rate limit", "429", "502", "503", "504",
            "connection", "network", "reset", "refused", "overloaded",
            "temporary", "transient", "busy",
        ]
        return any(p in error_str for p in retryable_patterns)
    
    async def execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function with retry logic."""
        last_error = None
        delay = self.config.base_delay
        
        for attempt in range(self.config.max_retries):
            try:
                result = func(*args, **kwargs) if not asyncio.iscoroutinefunction(func) else await func(*args, **kwargs)
                self._stats["successes"] += 1
                return result
            except Exception as e:
                last_error = e
                if not self.is_retryable(e) or attempt == self.config.max_retries - 1:
                    break
                
                self._stats["retries"] += 1
                delay = min(delay * self.config.exponential_base, self.config.max_delay)
                await asyncio.sleep(delay)
        
        self._stats["failures"] += 1
        raise last_error
    
    def get_retry_stats(self) -> dict:
        """Get retry statistics."""
        return dict(self._stats)


class ErrorRecovery:
    """Comprehensive error recovery system."""
    
    def __init__(self, project_path: str = "."):
        self.project_path = project_path
        self._recovery_strategies: dict[str, Callable] = {}
    
    def register_strategy(self, error_type: str, strategy: Callable):
        """Register a recovery strategy for an error type."""
        self._recovery_strategies[error_type] = strategy
    
    async def recover(self, tool_name: str, tool_args: dict, error: Exception) -> Any | None:
        """
        Attempt to recover from a tool execution error.
        
        Returns recovered result or None if recovery not possible.
        """
        error_str = str(error).lower()
        
        # Strategy 1: File not found — try to create parent directories
        if "no such file" in error_str or "not found" in error_str or "enoent" in error_str:
            file_path = tool_args.get("path", "")
            if file_path:
                try:
                    import os
                    parent = os.path.dirname(os.path.join(self.project_path, file_path))
                    os.makedirs(parent, exist_ok=True)
                    return {"recovered": True, "action": "created_parent_dirs", "path": parent}
                except Exception:
                    pass
        
        # Strategy 2: Permission denied — try with different approach
        if "permission" in error_str or "eacces" in error_str:
            return {"recovered": False, "suggestion": "Try running with elevated permissions or check file permissions."}
        
        # Strategy 3: Port already in use — suggest alternative
        if "address already in use" in error_str or "eaddrinuse" in error_str:
            return {"recovered": False, "suggestion": "Port is in use. Try a different port or kill the existing process."}
        
        # Strategy 4: Module not found — suggest install
        if "module not found" in error_str or "nomodulename" in error_str:
            import re
            match = re.search(r"No module named ['\"](.+?)['\"]", str(error))
            if match:
                module = match.group(1)
                return {"recovered": False, "suggestion": f"Install with: pip install {module}"}
        
        # Strategy 5: Connection refused — suggest checking service
        if "connection refused" in error_str:
            return {"recovered": False, "suggestion": "Service not running. Check if the server is started."}
        
        # Strategy 6: JSON decode error — suggest checking file format
        if "json" in error_str and ("decode" in error_str or "parse" in error_str):
            return {"recovered": False, "suggestion": "Invalid JSON. Check the file format and syntax."}
        
        # Strategy 7: Unicode/encoding error — suggest checking file encoding
        if "unicode" in error_str or "encoding" in error_str:
            return {"recovered": False, "suggestion": "Encoding error. Try specifying encoding='utf-8' or errors='replace'."}
        
        # Strategy 8: Timeout — suggest checking network or increasing timeout
        if "timeout" in error_str:
            return {"recovered": False, "suggestion": "Request timed out. Check network connection or increase timeout."}
        
        # Strategy 9: Out of memory — suggest reducing data size
        if "memory" in error_str or "oom" in error_str:
            return {"recovered": False, "suggestion": "Out of memory. Try reducing data size or processing in chunks."}
        
        # Strategy 10: NIM API errors
        if "404" in error_str and "page not found" in error_str:
            return {"recovered": False, "suggestion": "NIM API endpoint not found. Check if the API key is valid and the model is available."}
        if "401" in error_str or "unauthorized" in error_str:
            return {"recovered": False, "suggestion": "API key is invalid or expired. Run 'dev login' to update your key."}
        if "429" in error_str or "rate limit" in error_str:
            return {"recovered": False, "suggestion": "Rate limited. Wait a moment and try again, or add more API keys with 'dev setup'."}
        if "500" in error_str or "internal server error" in error_str:
            return {"recovered": False, "suggestion": "NIM server error. This is temporary — retry in a few seconds."}
        
        # Strategy 11: npm/node errors
        if "npm" in error_str and ("not found" in error_str or "enoent" in error_str):
            return {"recovered": False, "suggestion": "npm not found. Install Node.js first: https://nodejs.org"}
        if "package.json" in error_str and "not found" in error_str:
            return {"recovered": False, "suggestion": "No package.json found. Initialize with 'npm init -y'."}
        
        # Strategy 12: Import cycle errors
        if "import cycle" in error_str or "circular import" in error_str:
            return {"recovered": False, "suggestion": "Circular import detected. Refactor to break the cycle — move shared code to a separate module."}
        
        # Strategy 13: Syntax errors
        if "syntaxerror" in error_str or "syntax error" in error_str:
            import re
            line_match = re.search(r'line\s+(\d+)', str(error))
            line_info = f" at line {line_match.group(1)}" if line_match else ""
            return {"recovered": False, "suggestion": f"Python syntax error{line_info}. Check for missing colons, brackets, or indentation."}

        # Strategy 14: Type errors
        if "typeerror" in error_str or "type error" in error_str:
            return {"recovered": False, "suggestion": "Type mismatch. Check variable types and function signatures."}

        # Strategy 15: NameError (undefined variable)
        if "nameerror" in error_str or "name ' ' is not defined" in error_str:
            return {"recovered": False, "suggestion": "Undefined variable. Check for typos or missing imports."}
        
        # Strategy 16: Custom registered strategies
        for error_type, strategy in self._recovery_strategies.items():
            if error_type in error_str:
                try:
                    result = strategy(tool_name, tool_args, error)
                    if asyncio.iscoroutinefunction(result):
                        result = await result
                    return result
                except Exception:
                    pass
        
        return None


class ParallelExecutor:
    """Execute multiple tool calls in parallel."""
    
    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
    
    async def execute_parallel(self, tasks: list[tuple[Callable, tuple, dict]]) -> list[Any]:
        """Execute multiple tasks in parallel with concurrency limit."""
        async def _run(func, args, kwargs):
            async with self._semaphore:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
        
        coros = [_run(func, args, kwargs) for func, args, kwargs in tasks]
        return await asyncio.gather(*coros, return_exceptions=True)
    
    async def execute_batch(self, items: list[Any], handler: Callable) -> list[Any]:
        """Execute a handler for each item in parallel."""
        tasks = [(handler, (item,), {}) for item in items]
        return await self.execute_parallel(tasks)
