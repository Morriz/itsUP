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


# Add trace() method to Logger class
logging.Logger.trace = trace  # type: ignore[attr-defined]


class PathFormatter(logging.Formatter):
    """Custom formatter that shows relative file paths."""

    def format(self, record: logging.LogRecord) -> str:
        # Convert module name (monitor.core) to path (monitor/core.py)
        if record.name != '__main__':
            pathname = record.name.replace('.', '/') + '.py'
        else:
            # For __main__, use actual file path relative to project root
            pathname = os.path.relpath(record.pathname)

        # Create custom format with relative path
        record.custom_pathname = pathname
        return super().format(record)


def setup_logging(level: Optional[str] = None) -> None:
    """
    Setup logging with standardized format.

    Args:
        level: Log level (TRACE, DEBUG, INFO, WARNING, ERROR, CRITICAL)
               Defaults to LOG_LEVEL env var or INFO
    """
    level = level or os.getenv("LOG_LEVEL", "INFO").upper()

    # Convert string to level constant
    if level == "TRACE":
        level_const = TRACE
    else:
        level_const = getattr(logging, level, logging.INFO)

    formatter = PathFormatter(
        '[%(asctime)s] %(levelname)s > %(custom_pathname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S.%f'
    )

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(formatter)

    # Configure root logger
    logging.root.setLevel(level_const)
    logging.root.handlers = [console]
