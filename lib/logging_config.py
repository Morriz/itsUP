"""
Centralized logging configuration for itsUP.

TTY mode (interactive): Clean colored output with symbols
Non-TTY mode (pipes/logs): Full structured timestamps and paths
"""

import logging
import os
import sys
from datetime import datetime
from typing import Any, Optional

# Add TRACE level (below DEBUG)
TRACE = 5
logging.addLevelName(TRACE, "TRACE")


def trace(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    """Log trace message."""
    if self.isEnabledFor(TRACE):
        self._log(TRACE, message, args, **kwargs)  # pylint: disable=protected-access


# Add custom methods to Logger class
logging.Logger.trace = trace  # type: ignore[attr-defined]


class TTYAwareFormatter(logging.Formatter):
    """Formatter that adapts output based on TTY detection.

    TTY mode (interactive terminal):
        ✓ Migration complete!
        ⚠ Config needs review
        ✗ Failed to rename project

    Non-TTY mode (pipes, logs, automation):
        2025-11-04 00:11:48.166 INFO lib/migrations.py:97 Migration complete!
        2025-11-04 00:11:48.166 WARNING lib/migrations.py:71 Config needs review
        2025-11-04 00:11:48.166 ERROR lib/fixers/rename_ingress.py:62 Failed to rename project
    """

    # ANSI color codes
    GREY = "\033[90m"
    WHITE = "\033[97m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    RESET = "\033[0m"

    # Symbols for different log levels
    SYMBOLS = {
        "TRACE": "›",
        "DEBUG": "•",
        "INFO": "✓",
        "WARNING": "⚠",
        "ERROR": "✗",
        "CRITICAL": "✗",
    }

    # Colors for different log levels
    COLORS = {
        "TRACE": GREY,
        "DEBUG": CYAN,
        "INFO": GREEN,
        "WARNING": YELLOW,
        "ERROR": RED,
        "CRITICAL": RED,
    }

    def __init__(self, is_tty: bool):
        self.is_tty = is_tty
        if is_tty:
            # TTY: Clean output with just message
            super().__init__("%(message)s")
        else:
            # Non-TTY: Original format with > separator and line numbers (for logs/pipes/daemons)
            super().__init__("%(asctime)s %(levelname)s > %(custom_pathname)s:%(lineno)d: %(message)s")

    def formatTime(self, record: logging.LogRecord, datefmt: Optional[str] = None) -> str:
        """Format time with milliseconds support (for non-TTY mode)."""
        if not self.is_tty:
            ct = datetime.fromtimestamp(record.created)
            return ct.strftime("%Y-%m-%d %H:%M:%S") + f".{int(record.msecs):03d}"
        return super().formatTime(record, datefmt)

    def format(self, record: logging.LogRecord) -> str:
        # Add custom pathname for non-TTY mode
        if not self.is_tty:
            if record.name != "__main__":
                pathname = record.name.replace(".", "/") + ".py"
            else:
                pathname = os.path.relpath(record.pathname)
            record.custom_pathname = pathname

        # Format the base message
        message = super().format(record)

        if self.is_tty:
            # Add color and symbol for TTY
            symbol = self.SYMBOLS.get(record.levelname, "›")
            color = self.COLORS.get(record.levelname, self.WHITE)
            return f"{color}{symbol}{self.RESET} {message}"

        # Return structured format for non-TTY
        return message


def setup_logging(level: Optional[str] = None, log_file: Optional[str] = None) -> None:
    """
    Setup logging with TTY-aware formatting.

    Args:
        level: Log level (TRACE, DEBUG, INFO, WARNING, ERROR, CRITICAL)
               Defaults to LOG_LEVEL env var or INFO
        log_file: Optional file path to write logs to (in addition to console)

    Behavior:
        TTY (interactive): Clean colored output with symbols (✓ ⚠ ✗)
        Non-TTY (pipes): Full structured output with timestamps and paths
    """
    level = level or os.getenv("LOG_LEVEL", "INFO").upper()

    # Convert string to level constant
    if level == "TRACE":
        level_const = TRACE
    else:
        level_const = getattr(logging, level, logging.INFO)

    # Detect if stdout is a TTY (interactive terminal)
    is_tty = sys.stdout.isatty()

    handlers: list[logging.Handler] = []

    # Console handler with TTY-aware formatter
    console = logging.StreamHandler()
    console.setFormatter(TTYAwareFormatter(is_tty))
    handlers.append(console)

    # File handler (if specified) - always use structured format
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(TTYAwareFormatter(is_tty=False))  # Always structured for files
        handlers.append(file_handler)

    # Configure root logger
    logging.root.setLevel(level_const)
    logging.root.handlers = handlers
