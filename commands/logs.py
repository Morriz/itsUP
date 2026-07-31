"""Route itsUP runtime logs to the backend that owns each target."""

import json
import platform
import plistlib
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

import click
from instrukt_ai_logging.cli import iter_follow_lines
from instrukt_ai_logging.logging import parse_since

from commands.common import fail
from lib.paths import access_log_file, display_path


class LogTarget(StrEnum):
    """The closed set of runtime logs itsUP exposes."""

    API = "api"
    MONITOR = "monitor"
    BRINGUP = "bringup"
    APPLY = "apply"
    BACKUP = "backup"
    HEALTHCHECK = "healthcheck"
    ACCESS = "access"


@dataclass(frozen=True)
class LogDescriptor:
    """Describe one target and the backend identities that can serve it."""

    description: str
    linux_unit: str | None = None
    macos_agent: str | None = None


@dataclass(frozen=True)
class LogOptions:
    """The selection predicates shared by every backend."""

    follow: bool
    cutoff: datetime | None
    pattern: re.Pattern[str] | None


LOG_TARGETS: dict[LogTarget, LogDescriptor] = {
    LogTarget.API: LogDescriptor("API service requests and failures", "itsup-api", "api"),
    LogTarget.MONITOR: LogDescriptor("container security monitor lifecycle", "itsup-monitor"),
    LogTarget.BRINGUP: LogDescriptor("runtime bringup service", "itsup-bringup", "bringup"),
    LogTarget.APPLY: LogDescriptor("configuration apply service", "itsup-apply", "apply"),
    LogTarget.BACKUP: LogDescriptor("backup service", "itsup-backup", "backup"),
    LogTarget.HEALTHCHECK: LogDescriptor("host healthcheck service", "pi-healthcheck"),
    LogTarget.ACCESS: LogDescriptor("Traefik access records"),
}


def complete_log_target(ctx: click.Context, param: click.Parameter, incomplete: str) -> list[str]:
    """Complete log targets from the router's single target registry."""
    return [target.value for target in LogTarget if target.value.startswith(incomplete)]


def _fail(message: str) -> None:
    fail(message)
    raise SystemExit(1)


def _parse_target(value: str) -> LogTarget:
    try:
        return LogTarget(value)
    except ValueError as exc:
        valid_targets = ", ".join(target.value for target in LogTarget)
        _fail(f"Unknown log target: {value}. Valid targets: {valid_targets}")
        raise AssertionError("unreachable") from exc


def _parse_options(follow: bool, since: str | None, pattern: str | None) -> LogOptions:
    cutoff = None
    if since is not None:
        try:
            cutoff = datetime.now(timezone.utc) - parse_since(since)
        except ValueError as exc:
            _fail(f"Invalid --since value: {exc}")
            raise AssertionError("unreachable") from exc

    compiled_pattern = None
    if pattern is not None:
        try:
            compiled_pattern = re.compile(pattern)
        except re.error as exc:
            _fail(f"Invalid --grep pattern: {exc}")
            raise AssertionError("unreachable") from exc

    return LogOptions(follow=follow, cutoff=cutoff, pattern=compiled_pattern)


def _emit_if_selected(line: str, options: LogOptions) -> None:
    if options.pattern is None or options.pattern.search(line):
        click.echo(line, nl=False)


def _load_state(systemctl: str, unit: str) -> str | None:
    try:
        # systemctl has no project-provided or Python-native binding.
        result = subprocess.run(
            [systemctl, "show", unit, "--property=LoadState"],
            capture_output=True,
            check=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        return None

    key, separator, value = result.stdout.strip().partition("=")
    return value if key == "LoadState" and separator else None


def _journal_tools() -> tuple[str, str]:
    journalctl = shutil.which("journalctl")
    systemctl = shutil.which("systemctl")
    if journalctl is None:
        _fail("Cannot read unit logs: journalctl is not available.")
    if systemctl is None:
        _fail("Cannot inspect unit logs: systemctl is not available.")

    assert journalctl is not None
    assert systemctl is not None
    return journalctl, systemctl


def _require_loaded_unit(systemctl: str, unit: str) -> None:
    """Refuse a journal query when its unit is absent or unusable."""
    load_state = _load_state(systemctl, unit)
    if load_state == "loaded":
        return

    observed = load_state if load_state is not None else "unavailable"
    _fail(f"Cannot read {unit}: unit LoadState is {observed}.")


def _journal_command(journalctl: str, unit: str, options: LogOptions) -> list[str]:
    command = [journalctl, "-u", unit]
    if options.cutoff is not None:
        command.extend(["--since", options.cutoff.astimezone().strftime("%Y-%m-%d %H:%M:%S")])
    if options.follow:
        command.extend(["-n", "0", "-f"])
    return command


def _stream_journal(command: list[str], options: LogOptions, unit: str) -> None:
    try:
        # journalctl has no project-provided or Python-native binding.
        with subprocess.Popen(command, stdout=subprocess.PIPE, text=True) as process:
            if process.stdout is None:
                _fail(f"Cannot read {unit}: journalctl produced no output stream.")
            try:
                for line in process.stdout:
                    _emit_if_selected(line, options)
            except KeyboardInterrupt:
                process.terminate()
                return
            return_code = process.wait()
    except OSError as exc:
        _fail(f"Cannot read {unit}: unable to start journalctl ({exc}).")
        return

    if return_code != 0:
        raise SystemExit(return_code)


def _read_journal(unit: str, options: LogOptions) -> None:
    journalctl, systemctl = _journal_tools()
    _require_loaded_unit(systemctl, unit)
    _stream_journal(_journal_command(journalctl, unit, options), options, unit)


def _access_line_is_in_window(line: str, cutoff: datetime) -> bool:
    """Return whether a raw Traefik record proves it is inside the time window."""
    try:
        record = json.loads(line)
        if not isinstance(record, dict):
            return False
        timestamp = record.get("time", record.get("StartUTC"))
        if not isinstance(timestamp, str):
            return False
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return False
        return parsed.astimezone(timezone.utc) >= cutoff
    except (json.JSONDecodeError, ValueError, TypeError):
        return False


def _emit_file_line(line: str, options: LogOptions, *, is_access_log: bool) -> None:
    if options.cutoff is not None and (not is_access_log or not _access_line_is_in_window(line, options.cutoff)):
        return
    _emit_if_selected(line, options)


def _read_file(path: Path, options: LogOptions, *, is_access_log: bool) -> None:
    if not path.exists():
        _fail(f"Cannot read log file: {display_path(path)} does not exist.")

    try:
        if options.follow:
            for line in iter_follow_lines(path, start_at_end=True):
                _emit_file_line(line, options, is_access_log=is_access_log)
            return

        with path.open("r", encoding="utf-8", errors="replace", newline="") as log_file:
            for line in log_file:
                _emit_file_line(line, options, is_access_log=is_access_log)
    except KeyboardInterrupt:
        return
    except OSError as exc:
        _fail(f"Cannot read log file {display_path(path)}: {exc}.")


def _macos_log_file(agent: str) -> Path:
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"ai.itsup.{agent}.plist"
    if not plist_path.is_file():
        _fail(f"Cannot read macOS log: {display_path(plist_path)} does not exist.")

    try:
        with plist_path.open("rb") as plist_file:
            plist = plistlib.load(plist_file)
    except (OSError, plistlib.InvalidFileException) as exc:
        _fail(f"Cannot read macOS log configuration {display_path(plist_path)}: {exc}.")
        raise AssertionError("unreachable") from exc

    stdout_path = plist.get("StandardOutPath")
    if not isinstance(stdout_path, str) or not stdout_path:
        _fail(f"Cannot read macOS log: {display_path(plist_path)} has no StandardOutPath.")
    assert isinstance(stdout_path, str)
    return Path(stdout_path)


@click.command()
@click.argument("target", required=False, shell_complete=complete_log_target)
@click.option("--follow", "follow", "-f", is_flag=True, help="Print new records as they arrive.")
@click.option("--since", help="Select records from a duration such as 10m or 2h ago.")
@click.option("--grep", "pattern", help="Select records matching this case-sensitive regular expression.")
def logs(target: str | None, follow: bool, since: str | None, pattern: str | None) -> None:
    """View TARGET's runtime logs, or list the available targets."""
    if target is None:
        for log_target, descriptor in LOG_TARGETS.items():
            click.echo(f"{log_target.value} — {descriptor.description}")
        return

    log_target = _parse_target(target)
    options = _parse_options(follow, since, pattern)
    if log_target is LogTarget.ACCESS:
        _read_file(access_log_file(), options, is_access_log=True)
        return

    descriptor = LOG_TARGETS[log_target]
    operating_system = platform.system()
    if operating_system == "Linux" and descriptor.linux_unit is not None:
        _read_journal(descriptor.linux_unit, options)
        return

    if operating_system == "Darwin":
        if descriptor.macos_agent is None:
            _fail(f"{log_target.value} logs are available only on Linux.")
        if options.cutoff is not None:
            _fail("Cannot use --since for macOS unit logs: launchd output has no per-line timestamp.")
        _read_file(_macos_log_file(descriptor.macos_agent), options, is_access_log=False)
        return

    _fail(f"{log_target.value} logs are unavailable on {operating_system}.")
