"""
Structured logging for Dev Agent.

Provides consistent, leveled logging across all modules.
Supports DEBUG, INFO, WARNING, ERROR levels.
"""

import logging
import os
import sys
import time
from typing import Optional


# Log levels
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR


class DevLogger:
    """
    Structured logger for Dev Agent.
    
    Features:
    - Colored output in terminals
    - File logging when verbose mode is on
    - Module-specific loggers
    - Performance timing
    """

    def __init__(self, name: str = "dev", level: int = INFO, log_file: Optional[str] = None):
        self.name = name
        self.level = level
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level)
        
        # Avoid duplicate handlers
        if not self._logger.handlers:
            # Console handler with colors
            handler = logging.StreamHandler(sys.stderr)
            handler.setLevel(level)
            formatter = ColoredFormatter()
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)
            
            # File handler if specified
            if log_file:
                try:
                    os.makedirs(os.path.dirname(log_file), exist_ok=True)
                    file_handler = logging.FileHandler(log_file, encoding="utf-8")
                    file_handler.setLevel(DEBUG)
                    file_formatter = logging.Formatter(
                        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S",
                    )
                    file_handler.setFormatter(file_formatter)
                    self._logger.addHandler(file_handler)
                except Exception:
                    pass  # Intentional: non-critical: best-effort operation

    def debug(self, msg: str, *args, **kwargs):
        if self.level <= DEBUG:
            self._logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs):
        if self.level <= INFO:
            self._logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        if self.level <= WARNING:
            self._logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        if self.level <= ERROR:
            self._logger.error(msg, *args, **kwargs)

    def set_level(self, level: int):
        """Change log level dynamically."""
        self.level = level
        self._logger.setLevel(level)
        for handler in self._logger.handlers:
            handler.setLevel(level)

    def timer(self, label: str):
        """Context manager for timing operations."""
        return Timer(self, label)


class ColoredFormatter(logging.Formatter):
    """Formatter with ANSI color codes for terminal output."""
    
    COLORS = {
        logging.DEBUG: "\033[36m",     # Cyan
        logging.INFO: "\033[37m",      # White
        logging.WARNING: "\033[33m",   # Yellow
        logging.ERROR: "\033[31m",     # Red
    }
    RESET = "\033[0m"
    
    def format(self, record):
        color = self.COLORS.get(record.levelno, "")
        level = record.levelname.ljust(8)
        msg = record.getMessage()
        
        # Truncate long messages
        if len(msg) > 500:
            msg = msg[:497] + "..."
        
        return f"{color}{level}{self.RESET} {msg}"


class Timer:
    """Context manager for timing operations."""
    
    def __init__(self, logger: DevLogger, label: str):
        self.logger = logger
        self.label = label
        self.start: float = 0
    
    def __enter__(self):
        self.start = time.monotonic()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.monotonic() - self.start
        if elapsed > 1.0:
            self.logger.info(f"{self.label}: {elapsed:.2f}s")
        return False


# Module-level logger instances
_loggers: dict[str, DevLogger] = {}


def get_logger(name: str = "dev", level: int = INFO, log_file: Optional[str] = None) -> DevLogger:
    """Get or create a named logger."""
    if name not in _loggers:
        _loggers[name] = DevLogger(name=name, level=level, log_file=log_file)
    return _loggers[name]


def set_global_level(level: int):
    """Set log level for all loggers."""
    for logger in _loggers.values():
        logger.set_level(level)


# Convenience aliases
def log(msg: str, level: int = INFO):
    """Quick log to the default logger."""
    get_logger().log(level, msg)
