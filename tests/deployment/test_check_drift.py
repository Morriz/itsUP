"""Hermetic behavior test for `bin/install-bringup.sh --check-drift`.

Exercises the real render-and-compare mode directly: the mode is dispatched
before the installer's host-identity/canonical-checkout gate, so it runs here
with no root and no host membership. SERVICE_DIR is a fixture directory (its
env override already exists for the installer); templates are read from the
real REPO_ROOT `samples/systemd/` (no override — matching production). Every
case proves SERVICE_DIR is left untouched — this mode never writes.

Verifies `project/spec/api-surface#self-update`'s drift-detection contract — a
contract-defining declaration rather than a gherkin UC (TQ-01's sanctioned
exception): no feature spec owns the self-update sequence.
"""

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SYSTEMD_DIR = REPO_ROOT / "samples" / "systemd"
INSTALL_SCRIPT = REPO_ROOT / "bin" / "install-bringup.sh"

RENDER_VARS = {
    "ITSUP_USER": "testuser",
    "ITSUP_GROUP": "testgroup",
    "ITSUP_ROOT": str(REPO_ROOT),
    "ITSUP_HOME": "/home/testuser",
}

UNCHANGED_UNIT = "itsup-apply.timer"
CHANGED_UNIT = "itsup-backup.timer"
ABSENT_UNIT = "itsup-api.service"
FAULT_UNIT = "itsup-monitor.service"


def _render(unit_name: str) -> str:
    template = (SYSTEMD_DIR / unit_name).read_text(encoding="utf-8")
    return (
        template.replace("{{USER}}", RENDER_VARS["ITSUP_USER"])
        .replace("{{GROUP}}", RENDER_VARS["ITSUP_GROUP"])
        .replace("{{ROOT}}", RENDER_VARS["ITSUP_ROOT"])
        .replace("{{HOME}}", RENDER_VARS["ITSUP_HOME"])
    )


def _run_check_drift(service_dir: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, **RENDER_VARS, "SERVICE_DIR": str(service_dir)}
    return subprocess.run(
        [str(INSTALL_SCRIPT), "--check-drift"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _snapshot_tree(service_dir: Path) -> dict[str, tuple[float, str]]:
    """(mtime, content-or-marker) per entry — proves no write occurred."""
    snapshot = {}
    for entry in service_dir.iterdir():
        if entry.is_dir():
            snapshot[entry.name] = (entry.stat().st_mtime, "<dir>")
        else:
            snapshot[entry.name] = (entry.stat().st_mtime, entry.read_text(encoding="utf-8"))
    return snapshot


def test_unchanged_unit_is_silent_changed_and_absent_units_are_reported(tmp_path: Path) -> None:
    (tmp_path / UNCHANGED_UNIT).write_text(_render(UNCHANGED_UNIT), encoding="utf-8")
    (tmp_path / CHANGED_UNIT).write_text(_render(CHANGED_UNIT) + "\n# drifted\n", encoding="utf-8")
    # ABSENT_UNIT is deliberately never written.

    before = _snapshot_tree(tmp_path)
    result = _run_check_drift(tmp_path)
    after = _snapshot_tree(tmp_path)

    assert result.returncode == 0, result.stderr
    drifted = set(result.stdout.split())
    assert UNCHANGED_UNIT not in drifted
    assert CHANGED_UNIT in drifted
    assert ABSENT_UNIT in drifted
    assert before == after


def test_installed_directory_is_a_checker_error_not_drift(tmp_path: Path) -> None:
    (tmp_path / FAULT_UNIT).mkdir()

    before = _snapshot_tree(tmp_path)
    result = _run_check_drift(tmp_path)
    after = _snapshot_tree(tmp_path)

    assert result.returncode != 0
    assert FAULT_UNIT not in result.stdout.split()
    assert before == after


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permission checks")
def test_unreadable_installed_file_is_a_checker_error_not_drift(tmp_path: Path) -> None:
    """A `cmp` operational failure (dest_path unreadable) must not be folded
    into the same result as a genuine content difference — it is a checker
    error (non-zero exit), never reported as drift."""
    unreadable = tmp_path / FAULT_UNIT
    unreadable.write_text(_render(FAULT_UNIT), encoding="utf-8")
    unreadable.chmod(0o000)

    try:
        result = _run_check_drift(tmp_path)
    finally:
        unreadable.chmod(0o644)

    assert result.returncode != 0
    assert FAULT_UNIT not in result.stdout.split()
