"""Failure-alert composition and dispatch, plus the apply deadman assertion.

itsUP composes the alert; the operator's `alert.command` template owns the
transport (see `project/spec/itsup-config#alert-command`). This module never
names a transport and never writes a resolved secret to any diagnostic.
"""

import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from instrukt_ai_logging import get_logger

from lib.data import load_itsup_config, load_secrets

logger = get_logger(f"itsup.{__name__}")

JOURNAL_LINES = 20
JOURNAL_TIMEOUT_SECONDS = 10
DISPATCH_TIMEOUT_SECONDS = 30

DEADMAN_WINDOW_SECONDS = 26 * 60 * 60  # 03:00 cadence plus two hours slack
APPLY_STAMP_FILENAME = "apply-success"
DEADMAN_MARKER_FILENAME = "deadman-alerted"
DEADMAN_UNIT_IDENTITY = "itsup-apply-deadman"

DEFAULT_STATE_DIRECTORY = Path("/var/lib/itsup")
DEFAULT_RUNTIME_DIRECTORY = Path("/run/itsup")

_PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class AlertConfigError(Exception):
    """The `alert.command` boundary rejected the configured value."""


class AlertStatus(StrEnum):
    """Outcome category for a send-alert or deadman-assertion attempt."""

    SUPPRESSED = "suppressed"  # no command configured
    SENT = "sent"  # the command ran and exited zero
    FAILED = "failed"  # the command could not run, or exited non-zero
    SILENT = "silent"  # deadman only: apply is within the window
    SUPPRESSED_REPEAT = "suppressed_repeat"  # deadman only: already alerted for this stale period


@dataclass(frozen=True)
class AlertOutcome:
    """Result of a send-alert or deadman-assertion attempt.

    `detail` never carries a resolved argument or a raw exception message —
    see `project/spec/itsup-config#alert-command`.
    """

    status: AlertStatus
    detail: str


def send_alert(unit: str) -> AlertOutcome:
    """Compose and dispatch an alert for a unit that just entered `failed`."""
    config = load_itsup_config()
    argv_template = _resolve_command_template(config)
    if argv_template is None:
        return AlertOutcome(
            status=AlertStatus.SUPPRESSED,
            detail=f"alert.command not configured; suppressing alert for {unit}",
        )

    secrets = load_secrets(None)
    body = _compose_unit_body(unit)
    return _dispatch(argv_template, secrets, unit_identity=unit, body=body)


def check_deadman() -> AlertOutcome:
    """Assert the last successful apply is within the expected window.

    Guarded by a runtime-directory marker so one stale period yields exactly
    one alert; the marker is cleared on the next fresh observation so a later
    distinct stale period alerts again.
    """
    state_dir = _state_directory()
    runtime_dir = _runtime_directory()
    stamp = state_dir / APPLY_STAMP_FILENAME
    marker = runtime_dir / DEADMAN_MARKER_FILENAME

    age = _stamp_age_seconds(stamp)

    if age <= DEADMAN_WINDOW_SECONDS:
        marker.unlink(missing_ok=True)
        return AlertOutcome(status=AlertStatus.SILENT, detail="last successful apply is within the expected window")

    if marker.exists():
        return AlertOutcome(
            status=AlertStatus.SUPPRESSED_REPEAT, detail="deadman already alerted for this stale period"
        )

    # Written before dispatch, not after: a failed or crashed attempt must not
    # retry every 5 minutes for the rest of the stale period (D2's "not
    # retried" semantic extended to the deadman path).
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()

    detail_suffix = f"(age={_format_duration(age)}, window={_format_duration(DEADMAN_WINDOW_SECONDS)})"

    config = load_itsup_config()
    argv_template = _resolve_command_template(config)
    if argv_template is None:
        return AlertOutcome(
            status=AlertStatus.SUPPRESSED,
            detail=f"alert.command not configured; suppressing deadman alert {detail_suffix}",
        )

    secrets = load_secrets(None)
    body = _compose_deadman_body(age)
    return _dispatch(argv_template, secrets, unit_identity=DEADMAN_UNIT_IDENTITY, body=body)


def _resolve_command_template(config: dict[str, Any]) -> list[str] | None:
    """Extract and boundary-validate `alert.command`, pre-placeholder-resolution.

    Returns None only when the `alert` key or `alert.command` value is
    genuinely absent (missing or null) — a clean no-op. A malformed present
    value (a non-mapping `alert`, a non-string `command`, unparsable shell
    syntax, or an empty argument vector) raises `AlertConfigError` naming the
    offending key rather than being silently treated as unset.
    """
    alert_config = config.get("alert")
    if alert_config is None:
        return None
    if not isinstance(alert_config, dict):
        raise AlertConfigError(f"alert must be a mapping, got {type(alert_config).__name__}")

    template = alert_config.get("command")
    if template is None:
        return None

    if not isinstance(template, str):
        raise AlertConfigError(f"alert.command must be a string, got {type(template).__name__}")

    try:
        argv_template = shlex.split(template)
    except ValueError as exc:
        raise AlertConfigError(f"alert.command is not valid shell syntax: {exc}") from exc

    if not argv_template:
        raise AlertConfigError("alert.command splits to an empty argument vector")

    return argv_template


def _resolve_token(token: str, secrets: dict[str, str]) -> str:
    """Substitute `${VAR}` placeholders within one already-split argument."""

    def _replace(match: "re.Match[str]") -> str:
        name = match.group(1)
        value = secrets.get(name)
        if not value:
            raise AlertConfigError(f"alert.command references unresolved placeholder ${{{name}}}")
        return value

    return _PLACEHOLDER_RE.sub(_replace, token)


def _dispatch(argv_template: list[str], secrets: dict[str, str], *, unit_identity: str, body: str) -> AlertOutcome:
    """Resolve placeholders and run the operator's command, body on stdin.

    Never reports a resolved value, in any argument position — only the
    `alert.command` key's pre-resolution executable token and the exit code.
    """
    argv = [_resolve_token(token, secrets) for token in argv_template]
    env = {**os.environ, "ITSUP_ALERT_UNIT": unit_identity}

    try:
        # The operator's configured transport is an arbitrary external
        # executable named only in projects/itsup.yml; there is no Python-
        # native alternative to running it.
        result = subprocess.run(
            argv,
            input=body,
            capture_output=True,
            text=True,
            env=env,
            shell=False,
            check=False,
            timeout=DISPATCH_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return AlertOutcome(
            status=AlertStatus.FAILED,
            detail=f"alert.command ({argv_template[0]}) failed to execute",
        )

    if result.returncode != 0:
        return AlertOutcome(
            status=AlertStatus.FAILED,
            detail=f"alert.command ({argv_template[0]}) exited with status {result.returncode}",
        )

    return AlertOutcome(status=AlertStatus.SENT, detail=f"alert dispatched for {unit_identity}")


def _read_journal(unit: str) -> tuple[str, bool]:
    """Return the unit's last journal lines, and whether the read degraded."""
    try:
        # journalctl is systemd's own journal reader; no Python-native API
        # reads the systemd journal without adding a new dependency.
        result = subprocess.run(
            ["journalctl", "-u", unit, "-n", str(JOURNAL_LINES), "--no-pager"],
            capture_output=True,
            text=True,
            timeout=JOURNAL_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("alert: journal read failed for %s: %s", unit, exc)
        return "", True

    if result.returncode != 0:
        logger.warning("alert: journalctl exited %s for %s", result.returncode, unit)
        return "", True

    return result.stdout, False


def _compose_unit_body(unit: str) -> str:
    """Compose the alert body for a failed unit: identity plus journal context.

    The failure event must still escape even when journal context is
    unavailable — an alert without context beats no alert — so a degraded
    read composes an explicit marker rather than a shorter, unmarked body.
    """
    journal_text, degraded = _read_journal(unit)
    lines = [f"itsUP alert: unit {unit} failed", ""]
    if degraded:
        lines.append("(journal context unavailable — see the alert composer's diagnostic log)")
    else:
        lines.append(f"Last {JOURNAL_LINES} journal lines:")
        lines.append(journal_text)
    return "\n".join(lines)


def _compose_deadman_body(age_seconds: float) -> str:
    return (
        f"itsUP alert: deadman assertion tripped\n"
        f"Last successful apply is stale: age={_format_duration(age_seconds)}, "
        f"window={_format_duration(DEADMAN_WINDOW_SECONDS)}"
    )


def _format_duration(seconds: float) -> str:
    if seconds == float("inf"):
        return "unknown (no successful apply recorded)"
    return f"{seconds / 3600:.1f}h"


def _state_directory() -> Path:
    """Resolve the state directory from the supervisor's exported environment."""
    value = os.environ.get("STATE_DIRECTORY")
    return Path(value) if value else DEFAULT_STATE_DIRECTORY


def _runtime_directory() -> Path:
    """Resolve the runtime directory from the supervisor's exported environment."""
    value = os.environ.get("RUNTIME_DIRECTORY")
    return Path(value) if value else DEFAULT_RUNTIME_DIRECTORY


def _stamp_age_seconds(stamp: Path) -> float:
    """Age of the last-successful-apply stamp; a missing stamp counts as stale."""
    try:
        mtime = stamp.stat().st_mtime
    except FileNotFoundError:
        return float("inf")
    return time.time() - mtime
