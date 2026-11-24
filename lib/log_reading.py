"""Read-side primitives for log files: a duration grammar and a file follower."""

import os
import time
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import BinaryIO

_POLL_INTERVAL_SECONDS = 0.25
_DURATION_UNITS = {
    "s": timedelta(seconds=1),
    "m": timedelta(minutes=1),
    "h": timedelta(hours=1),
    "d": timedelta(days=1),
}


def parse_duration(value: str) -> timedelta:
    """Parse a whole number followed by a unit from `_DURATION_UNITS`."""
    text = value.strip().lower()
    number, unit = text[:-1], text[-1:]
    if not (number.isascii() and number.isdigit()) or unit not in _DURATION_UNITS:
        units = ", ".join(_DURATION_UNITS)
        raise ValueError(f"expected a whole number followed by one of {units}, got {value!r}")
    return int(number) * _DURATION_UNITS[unit]


def follow_lines(path: Path) -> Iterator[str]:
    """Yield each line written to `path` from now on; never returns.

    A file present at the start is followed from its end. A file that appears
    later, replaces the followed one at the same path, or is truncated in place
    is read from its start.
    """
    skip_existing = True
    while True:
        try:
            log_file = path.open("rb")
        except FileNotFoundError:
            skip_existing = False
            time.sleep(_POLL_INTERVAL_SECONDS)
            continue
        with log_file:
            if skip_existing:
                log_file.seek(0, os.SEEK_END)
                skip_existing = False
            yield from _lines_while_current(log_file, path)


def _lines_while_current(log_file: BinaryIO, path: Path) -> Iterator[str]:
    """Yield complete lines from the open file for as long as `path` still names it.

    A line whose end has not arrived when the file stops being current is
    yielded as it stands.
    """
    inode = os.fstat(log_file.fileno()).st_ino
    pending = b""
    while True:
        pending += log_file.readline()
        if pending.endswith(b"\n"):
            yield pending.decode("utf-8", errors="replace")
            pending = b""
        elif _is_current(log_file, path, inode):
            time.sleep(_POLL_INTERVAL_SECONDS)
        else:
            break
    if pending:
        yield pending.decode("utf-8", errors="replace")


def _is_current(log_file: BinaryIO, path: Path, inode: int) -> bool:
    """Return whether `path` still names the open file and has not been truncated below the read position."""
    try:
        status = path.stat()
    except FileNotFoundError:
        return False
    return status.st_ino == inode and status.st_size >= log_file.tell()
