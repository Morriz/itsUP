#!/usr/bin/env python3

"""Follow log files with smart formatting"""

import logging
import os
import subprocess
import sys
from pathlib import Path

import click

logger = logging.getLogger(__name__)

LOGS_DIR = Path("logs")
FORMAT_LOGS_SCRIPT = Path("bin/format-logs.py")

# Logs that contain JSON and need formatting
JSON_LOGS = {"access"}


def get_available_logs():
    """Get list of available log files (without .log extension)."""
    if not LOGS_DIR.exists():
        return []

    logs = []
    for log_file in LOGS_DIR.glob("*.log"):
        if log_file.name.endswith(".log") and not log_file.name.endswith((".log.1", ".log.2")):
            log_name = log_file.stem  # Remove .log extension
            logs.append(log_name)

    return sorted(logs)


def complete_log_names(ctx, param, incomplete):
    """Autocomplete log names."""
    available = get_available_logs()
    return [name for name in available if name.startswith(incomplete)]


@click.command()
@click.argument("names", nargs=-1, shell_complete=complete_log_names)
@click.option("-n", "--lines", default=100, type=int, help="Number of initial lines to show (default: 100)")
def logs(names, lines):
    """
    📜 Follow log files with smart formatting

    Tails log files from the logs/ directory. JSON logs (like access.log)
    are automatically formatted for readability. Output is clean without
    file name separators.

    \b
    Examples:
        itsup logs                  # Follow all logs
        itsup logs access           # Follow access.log only
        itsup logs api monitor      # Follow api.log and monitor.log
        itsup logs access -n 50     # Show last 50 lines initially
    """
    # Determine which logs to follow
    if names:
        log_names = list(names)
    else:
        # Default to all logs
        log_names = get_available_logs()

    if not log_names:
        click.echo("No log files found in logs/", err=True)
        sys.exit(1)

    # Validate all requested logs exist
    available = get_available_logs()
    for name in log_names:
        if name not in available:
            click.echo(f"Error: Log file '{name}.log' not found", err=True)
            click.echo(f"Available: {', '.join(available)}", err=True)
            sys.exit(1)

    # Build list of log files
    log_files = [str(LOGS_DIR / f"{name}.log") for name in log_names]

    # Determine if we need formatting (if any JSON logs are included)
    needs_formatting = any(name in JSON_LOGS for name in log_names)

    try:
        if needs_formatting:
            # Tail logs and pipe through formatter
            # Use -q to suppress filename headers when multiple files
            tail_args = [f"-n{lines}", "-F"]
            if len(log_files) > 1:
                tail_args.insert(0, "-q")
            tail_cmd = ["tail"] + tail_args + log_files
            format_cmd = [str(FORMAT_LOGS_SCRIPT)]

            logger.debug(f"Running: {' '.join(tail_cmd)} | {' '.join(format_cmd)}")

            # Start tail process
            tail_proc = subprocess.Popen(
                tail_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,  # Suppress any error messages
                text=True
            )

            # Start formatter process
            format_proc = subprocess.Popen(
                format_cmd,
                stdin=tail_proc.stdout,
                stdout=sys.stdout,
                text=True
            )

            # Close tail's stdout in parent to allow SIGPIPE
            tail_proc.stdout.close()

            # Wait for formatter (will exit when tail exits)
            format_proc.wait()

        else:
            # Just tail without formatting
            # Use -q to suppress filename headers when multiple files
            tail_args = [f"-n{lines}", "-F"]
            if len(log_files) > 1:
                tail_args.insert(0, "-q")
            cmd = ["tail"] + tail_args + log_files

            logger.debug(f"Running: {' '.join(cmd)}")

            subprocess.run(
                cmd,
                stderr=subprocess.DEVNULL,  # Suppress any error messages
                check=True
            )

    except KeyboardInterrupt:
        # Clean exit on Ctrl+C
        sys.exit(0)
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to tail logs: {e}")
        sys.exit(e.returncode)
