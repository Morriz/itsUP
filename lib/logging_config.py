"""
Centralized logging configuration for itsUP.

Provides standardized log format across all modules:
[2025-10-23 23:05:31.454670] INFO > path/to/file.py: message
"""

import logging
import os
from typing import Any, Optional

# Add TRACE level (below DEBUG)
TRACE = 5
logging.addLevelName(TRACE, "TRACE")


def trace(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    """Log trace message."""
    if self.isEnabledFor(TRACE):
        self._log(TRACE, message, args, **kwargs)  # pylint: disable=protected-access


def log_legacy(self: logging.Logger, message: str, *args: Any, level: str = "INFO", **kwargs: Any) -> None:
    """Log message with legacy level name format (for backward compatibility)."""
    level_map = {
        "TRACE": TRACE,
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARN": logging.WARNING,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    level_const = level_map.get(level.upper(), logging.INFO)
    if self.isEnabledFor(level_const):
        self._log(level_const, message, args, **kwargs)  # pylint: disable=protected-access


# Add custom methods to Logger class
logging.Logger.trace = trace  # type: ignore[attr-defined]
logging.Logger.log_legacy = log_legacy  # type: ignore[attr-defined]


class PathFormatter(logging.Formatter):
    """Custom formatter that shows relative file paths and milliseconds."""

    def formatTime(self, record: logging.LogRecord, datefmt: Optional[str] = None) -> str:
        """Format time with milliseconds support."""
        from datetime import datetime

        ct = datetime.fromtimestamp(record.created)
        if datefmt:
            # Remove .%f from format (strftime outputs 6-digit microseconds, we want 3-digit milliseconds)
            if ".%f" in datefmt:
                datefmt_no_frac = datefmt.replace(".%f", "")
                return ct.strftime(datefmt_no_frac) + f".{int(record.msecs):03d}"
            return ct.strftime(datefmt)
        return ct.strftime("%Y-%m-%d %H:%M:%S") + f".{int(record.msecs):03d}"

    def format(self, record: logging.LogRecord) -> str:
        # Convert module name (monitor.core) to path (monitor/core.py)
        if record.name != "__main__":
            pathname = record.name.replace(".", "/") + ".py"
        else:
            # For __main__, use actual file path relative to project root
            pathname = os.path.relpath(record.pathname)

        # Create custom format with relative path
        record.custom_pathname = pathname
        return super().format(record)


def setup_logging(level: Optional[str] = None, log_file: Optional[str] = None) -> None:
    """
    Setup logging with standardized format.

    Args:
        level: Log level (TRACE, DEBUG, INFO, WARNING, ERROR, CRITICAL)
               Defaults to LOG_LEVEL env var or INFO
        log_file: Optional file path to write logs to (in addition to console)
    """
    level = level or os.getenv("LOG_LEVEL", "INFO").upper()

    # Convert string to level constant
    if level == "TRACE":
        level_const = TRACE
    else:
        level_const = getattr(logging, level, logging.INFO)

    formatter = PathFormatter(
        "%(asctime)s %(levelname)s > %(custom_pathname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S.%f"
    )

    handlers: list[logging.Handler] = []

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    handlers.append(console)

    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    # Configure root logger
    logging.root.setLevel(level_const)
    logging.root.handlers = handlers
