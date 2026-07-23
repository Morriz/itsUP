"""Behavioral tests for itsUP's transport-agnostic ops failure alerting.

Every test drives bin/alert.py as a subprocess — the surface systemd invokes —
against an isolated ITSUP_ROOT, with STATE_DIRECTORY/RUNTIME_DIRECTORY pointed
at temp directories (mirroring the supervisor-exported environment) and
XDG_STATE_HOME isolated so configure_logging never touches host state.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ALERT_SCRIPT = REPO_ROOT / "bin" / "alert.py"
SPEC_ID = "project/spec/feature/operations/failure-alerting"

JOURNAL_FIXTURE = "Jul 22 03:00:01 host unit[123]: starting\nJul 22 03:00:02 host unit[123]: fatal error\n"
FAILED_UNIT = "itsup-apply.service"


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


def _write_recording_transport(path: Path, *, exit_code: int = 0) -> None:
    """A real executable recording each call's argv + stdin + ITSUP_ALERT_UNIT."""
    _write_executable(
        path,
        f"""#!/usr/bin/env bash
set -euo pipefail
dir="$(dirname "$0")"
n=0
while [ -f "$dir/call-$n.argv" ]; do n=$((n+1)); done
printf '%s\\n' "$@" > "$dir/call-$n.argv"
cat > "$dir/call-$n.stdin"
printf '%s' "${{ITSUP_ALERT_UNIT:-}}" > "$dir/call-$n.unit"
exit {exit_code}
""",
    )


def _write_journalctl_fake(path: Path, *, exit_code: int = 0) -> None:
    if exit_code == 0:
        body = f"""#!/usr/bin/env bash
set -euo pipefail
cat <<'JOURNAL'
{JOURNAL_FIXTURE}JOURNAL
"""
    else:
        body = f"""#!/usr/bin/env bash
set -euo pipefail
exit {exit_code}
"""
    _write_executable(path, body)


def _write_config(root: Path, *, alert_command: str | None) -> None:
    projects_dir = root / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    alert_block = f"alert:\n  command: '{alert_command}'\n" if alert_command else ""
    (projects_dir / "itsup.yml").write_text(f"traefikDomain: traefik.example.com\n{alert_block}")


def _write_secrets(root: Path, secrets: dict[str, str]) -> None:
    secrets_dir = root / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    lines = "".join(f"{key}={value}\n" for key, value in secrets.items())
    (secrets_dir / "itsup.txt").write_text(lines)


def _call_files(recorder_dir: Path) -> list[Path]:
    return sorted(recorder_dir.glob("call-*.argv"), key=lambda p: int(p.stem.split("-")[1]))


def _run_alert(
    root: Path,
    args: list[str],
    *,
    fake_bin: Path,
    state_dir: Path,
    runtime_dir: Path,
    log_home: Path,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["ITSUP_ROOT"] = str(root)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["STATE_DIRECTORY"] = str(state_dir)
    env["RUNTIME_DIRECTORY"] = str(runtime_dir)
    env["XDG_STATE_HOME"] = str(log_home)
    return subprocess.run(
        [sys.executable, str(ALERT_SCRIPT), *args],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.fixture
def env_dirs(tmp_path: Path) -> dict[str, Path]:
    dirs = {
        "root": tmp_path / "root",
        "fake_bin": tmp_path / "fake-bin",
        "state_dir": tmp_path / "state",
        "runtime_dir": tmp_path / "runtime",
        "log_home": tmp_path / "log-home",
        "recorder_dir": tmp_path / "recorder",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-OFA1")
def test_uc_ofa1_failed_unit_alerts_once_with_journal_context(
    env_dirs: dict[str, Path], snapshot: SnapshotAssertion
) -> None:
    """UC-OFA1: a failed unit alerts exactly once, body carries journal context."""
    root, fake_bin, recorder_dir = env_dirs["root"], env_dirs["fake_bin"], env_dirs["recorder_dir"]
    transport = recorder_dir / "transport.sh"
    _write_recording_transport(transport, exit_code=0)
    _write_journalctl_fake(fake_bin / "journalctl", exit_code=0)
    _write_config(root, alert_command=str(transport))

    result = _run_alert(
        root,
        [FAILED_UNIT],
        fake_bin=fake_bin,
        state_dir=env_dirs["state_dir"],
        runtime_dir=env_dirs["runtime_dir"],
        log_home=env_dirs["log_home"],
    )

    assert result.returncode == 0, result.stderr
    calls = _call_files(recorder_dir)
    assert len(calls) == 1
    assert (recorder_dir / "call-0.unit").read_text() == FAILED_UNIT
    body = (recorder_dir / "call-0.stdin").read_text()
    assert body == snapshot


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-OFA2")
def test_uc_ofa2_unset_key_is_a_clean_noop(env_dirs: dict[str, Path]) -> None:
    """UC-OFA2: with no alert.command configured, no command runs and the run succeeds."""
    root, fake_bin, recorder_dir = env_dirs["root"], env_dirs["fake_bin"], env_dirs["recorder_dir"]
    _write_journalctl_fake(fake_bin / "journalctl", exit_code=0)
    _write_config(root, alert_command=None)

    result = _run_alert(
        root,
        [FAILED_UNIT],
        fake_bin=fake_bin,
        state_dir=env_dirs["state_dir"],
        runtime_dir=env_dirs["runtime_dir"],
        log_home=env_dirs["log_home"],
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()
    assert not _call_files(recorder_dir)


@pytest.mark.functional
def test_malformed_alert_value_fails_fast_instead_of_suppressing(env_dirs: dict[str, Path]) -> None:
    """A non-mapping `alert:` value is a boundary error, not a clean no-op.

    Verifies project/spec/itsup-config#alert-command's fail-fast boundary
    contract — distinct from UC-OFA2, where the key is genuinely absent — a
    contract-defining declaration rather than a gherkin UC (TQ-01's sanctioned
    exception).
    """
    root, fake_bin, recorder_dir = env_dirs["root"], env_dirs["fake_bin"], env_dirs["recorder_dir"]
    _write_journalctl_fake(fake_bin / "journalctl", exit_code=0)
    projects_dir = root / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    (projects_dir / "itsup.yml").write_text("traefikDomain: traefik.example.com\nalert: not-a-mapping\n")

    result = _run_alert(
        root,
        [FAILED_UNIT],
        fake_bin=fake_bin,
        state_dir=env_dirs["state_dir"],
        runtime_dir=env_dirs["runtime_dir"],
        log_home=env_dirs["log_home"],
    )

    assert result.returncode != 0
    assert result.stderr.strip()
    assert not _call_files(recorder_dir)


@pytest.mark.functional
def test_malformed_shell_syntax_fails_fast_with_no_transport_execution(
    env_dirs: dict[str, Path], snapshot: SnapshotAssertion
) -> None:
    """An `alert.command` with unmatched shell quoting is a controlled boundary
    error — not an uncaught exception — and the configured transport never runs.

    Verifies project/spec/itsup-config#alert-command's fail-fast boundary
    contract for unparsable shell syntax — a contract-defining declaration
    rather than a gherkin UC (TQ-01's sanctioned exception).
    """
    root, fake_bin, recorder_dir = env_dirs["root"], env_dirs["fake_bin"], env_dirs["recorder_dir"]
    transport = recorder_dir / "transport.sh"
    _write_recording_transport(transport, exit_code=0)
    _write_journalctl_fake(fake_bin / "journalctl", exit_code=0)
    _write_config(root, alert_command=f'{transport} "unterminated')

    result = _run_alert(
        root,
        [FAILED_UNIT],
        fake_bin=fake_bin,
        state_dir=env_dirs["state_dir"],
        runtime_dir=env_dirs["runtime_dir"],
        log_home=env_dirs["log_home"],
    )

    assert result.returncode != 0
    # A snapshot of the full stderr, not a substring, is what proves this is
    # the controlled one-line AlertConfigError diagnostic rather than an
    # uncaught traceback — an uncaught ValueError would also produce a
    # non-zero exit and non-empty stderr, but its content would not match.
    assert result.stderr == snapshot
    assert not _call_files(recorder_dir)


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-OFA4")
def test_uc_ofa4_secret_with_metacharacters_stays_one_argument(env_dirs: dict[str, Path]) -> None:
    """UC-OFA4: a secret carrying whitespace and shell metacharacters arrives as one argument."""
    root, fake_bin, recorder_dir = env_dirs["root"], env_dirs["fake_bin"], env_dirs["recorder_dir"]
    transport = recorder_dir / "transport.sh"
    _write_recording_transport(transport, exit_code=0)
    _write_journalctl_fake(fake_bin / "journalctl", exit_code=0)
    dangerous_value = "ops; rm -rf / && echo pwned # with spaces"
    _write_config(root, alert_command=f"{transport} --to ${{CHANNEL}}")
    _write_secrets(root, {"CHANNEL": dangerous_value})

    result = _run_alert(
        root,
        ["itsup-backup.service"],
        fake_bin=fake_bin,
        state_dir=env_dirs["state_dir"],
        runtime_dir=env_dirs["runtime_dir"],
        log_home=env_dirs["log_home"],
    )

    assert result.returncode == 0, result.stderr
    calls = _call_files(recorder_dir)
    assert len(calls) == 1
    argv = calls[0].read_text().splitlines()
    assert argv == ["--to", dangerous_value]


@pytest.mark.functional
def test_journal_read_failure_marks_the_body_degraded(env_dirs: dict[str, Path], snapshot: SnapshotAssertion) -> None:
    """A journalctl failure still lets the alert escape, with an explicit degradation marker.

    Verifies project/spec/itsup-config#alert-command's composer contract that an
    alert without journal context beats no alert at all — not its own UC, but a
    contract-defining declaration of that spec (TQ-01's sanctioned exception).
    """
    root, fake_bin, recorder_dir = env_dirs["root"], env_dirs["fake_bin"], env_dirs["recorder_dir"]
    transport = recorder_dir / "transport.sh"
    _write_recording_transport(transport, exit_code=0)
    _write_journalctl_fake(fake_bin / "journalctl", exit_code=1)
    _write_config(root, alert_command=str(transport))

    result = _run_alert(
        root,
        [FAILED_UNIT],
        fake_bin=fake_bin,
        state_dir=env_dirs["state_dir"],
        runtime_dir=env_dirs["runtime_dir"],
        log_home=env_dirs["log_home"],
    )

    assert result.returncode == 0, result.stderr
    body = (recorder_dir / "call-0.stdin").read_text()
    assert body == snapshot


@pytest.mark.functional
def test_secret_leak_absent_when_command_fails(env_dirs: dict[str, Path]) -> None:
    """A later-argument secret never appears in stdout, stderr, or the diagnostic log
    when the configured command exits non-zero.

    Verifies project/spec/itsup-config#alert-command's "failure diagnostics never
    name any resolved value" contract — a contract-defining declaration rather
    than a gherkin UC (TQ-01's sanctioned exception).
    """
    root, fake_bin, recorder_dir = env_dirs["root"], env_dirs["fake_bin"], env_dirs["recorder_dir"]
    transport = recorder_dir / "transport.sh"
    _write_recording_transport(transport, exit_code=1)
    _write_journalctl_fake(fake_bin / "journalctl", exit_code=0)
    secret_value = "super-secret-token-xyz"
    _write_config(root, alert_command=f"{transport} --to ${{CHANNEL}}")
    _write_secrets(root, {"CHANNEL": secret_value})

    result = _run_alert(
        root,
        ["itsup-backup.service"],
        fake_bin=fake_bin,
        state_dir=env_dirs["state_dir"],
        runtime_dir=env_dirs["runtime_dir"],
        log_home=env_dirs["log_home"],
    )

    assert result.returncode != 0
    assert secret_value not in result.stdout
    assert secret_value not in result.stderr
    log_file = env_dirs["log_home"] / "instrukt-ai" / "itsup" / "alert.log"
    assert log_file.exists()
    assert secret_value not in log_file.read_text()


@pytest.mark.functional
def test_secret_leak_absent_when_executable_is_missing(env_dirs: dict[str, Path]) -> None:
    """A secret sitting in argument zero never appears anywhere when the resolved
    executable does not exist (the execution-failure path, not a non-zero exit).

    Verifies project/spec/itsup-config#alert-command's contract that diagnostics
    exclude rendering the underlying execution exception, which would otherwise
    carry the resolved path — a contract-defining declaration (TQ-01's sanctioned
    exception).
    """
    root, fake_bin, recorder_dir = env_dirs["root"], env_dirs["fake_bin"], env_dirs["recorder_dir"]
    _write_journalctl_fake(fake_bin / "journalctl", exit_code=0)
    secret_value = f"{recorder_dir}/nonexistent-binary-xyz"
    _write_config(root, alert_command="${TRANSPORT_BIN} --to ops")
    _write_secrets(root, {"TRANSPORT_BIN": secret_value})

    result = _run_alert(
        root,
        ["itsup-backup.service"],
        fake_bin=fake_bin,
        state_dir=env_dirs["state_dir"],
        runtime_dir=env_dirs["runtime_dir"],
        log_home=env_dirs["log_home"],
    )

    assert result.returncode != 0
    assert secret_value not in result.stdout
    assert secret_value not in result.stderr
    log_file = env_dirs["log_home"] / "instrukt-ai" / "itsup" / "alert.log"
    assert log_file.exists()
    assert secret_value not in log_file.read_text()


def _set_stamp_age(state_dir: Path, *, age_hours: float | None) -> None:
    """Write (or omit) the apply-success stamp with an mtime `age_hours` old."""
    stamp = state_dir / "apply-success"
    if age_hours is None:
        stamp.unlink(missing_ok=True)
        return
    stamp.touch()
    now = time.time()
    os.utime(stamp, (now, now - age_hours * 3600))


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-OFA5")
def test_uc_ofa5_stale_apply_trips_the_deadman_once_per_period(env_dirs: dict[str, Path]) -> None:
    """UC-OFA5: a stale apply alerts once; a repeat within the same period is suppressed,
    and a later distinct stale period alerts again."""
    root, fake_bin, recorder_dir = env_dirs["root"], env_dirs["fake_bin"], env_dirs["recorder_dir"]
    transport = recorder_dir / "transport.sh"
    _write_recording_transport(transport, exit_code=0)
    _write_journalctl_fake(fake_bin / "journalctl", exit_code=0)
    _write_config(root, alert_command=str(transport))
    state_dir, runtime_dir = env_dirs["state_dir"], env_dirs["runtime_dir"]

    _set_stamp_age(state_dir, age_hours=30)
    first = _run_alert(
        root,
        ["--deadman"],
        fake_bin=fake_bin,
        state_dir=state_dir,
        runtime_dir=runtime_dir,
        log_home=env_dirs["log_home"],
    )
    assert first.returncode == 0, first.stderr
    assert len(_call_files(recorder_dir)) == 1

    repeat = _run_alert(
        root,
        ["--deadman"],
        fake_bin=fake_bin,
        state_dir=state_dir,
        runtime_dir=runtime_dir,
        log_home=env_dirs["log_home"],
    )
    assert repeat.returncode == 0, repeat.stderr
    assert len(_call_files(recorder_dir)) == 1

    _set_stamp_age(state_dir, age_hours=1)
    fresh = _run_alert(
        root,
        ["--deadman"],
        fake_bin=fake_bin,
        state_dir=state_dir,
        runtime_dir=runtime_dir,
        log_home=env_dirs["log_home"],
    )
    assert fresh.returncode == 0, fresh.stderr
    assert len(_call_files(recorder_dir)) == 1
    assert not (runtime_dir / "deadman-alerted").exists()

    _set_stamp_age(state_dir, age_hours=27)
    second_period = _run_alert(
        root,
        ["--deadman"],
        fake_bin=fake_bin,
        state_dir=state_dir,
        runtime_dir=runtime_dir,
        log_home=env_dirs["log_home"],
    )
    assert second_period.returncode == 0, second_period.stderr
    assert len(_call_files(recorder_dir)) == 2


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-OFA6")
def test_uc_ofa6_fresh_apply_keeps_the_deadman_silent(env_dirs: dict[str, Path]) -> None:
    """UC-OFA6: a fresh last-successful-apply produces no alert."""
    root, fake_bin, recorder_dir = env_dirs["root"], env_dirs["fake_bin"], env_dirs["recorder_dir"]
    transport = recorder_dir / "transport.sh"
    _write_recording_transport(transport, exit_code=0)
    _write_journalctl_fake(fake_bin / "journalctl", exit_code=0)
    _write_config(root, alert_command=str(transport))
    state_dir, runtime_dir = env_dirs["state_dir"], env_dirs["runtime_dir"]

    _set_stamp_age(state_dir, age_hours=1)
    result = _run_alert(
        root,
        ["--deadman"],
        fake_bin=fake_bin,
        state_dir=state_dir,
        runtime_dir=runtime_dir,
        log_home=env_dirs["log_home"],
    )

    assert result.returncode == 0, result.stderr
    assert not _call_files(recorder_dir)
