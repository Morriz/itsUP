"""Hermetic contracts for the failure-alert unit templates and installer wiring.

No live unit is started and neither runtime target (`make install-runtime` /
`make uninstall-runtime`) is executed — both would mutate the shared host.
Verification is read-only: rendered-unit inspection, `systemd-analyze verify`
(a validation command that starts nothing), and installer/uninstaller source
text. This is the supervisor-boundary structural proof that carries UC-OFA3
(a successful run produces no alert): OnFailure= cannot fire on success, and
the exclusivity check below rules out an added OnSuccess= path.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SYSTEMD_DIR = REPO_ROOT / "samples" / "systemd"

ALERT_TEMPLATE = "itsup-alert@.service"
ALERT_REFERENCE_MARKER = "itsup-alert@"
ON_FAILURE_PREFIX = "OnFailure="
ALERT_ON_FAILURE = "OnFailure=itsup-alert@%n.service"
ALERT_UNIT_ARRAY_ENTRY = '"itsup-alert@.service"'
SYSTEMD_JOURNAL_GROUP = "systemd-journal"
DEADMAN_GUARD_PATTERN = 'bin/alert.py" --deadman || log'

COVERED_UNITS = (
    "itsup-bringup.service",
    "itsup-apply.service",
    "itsup-apply.timer",
    "itsup-backup.service",
    "itsup-backup.timer",
    "pi-healthcheck.service",
    "pi-healthcheck.timer",
    "itsup-api.service",
    "itsup-monitor.service",
)

STAMPED_UNITS = ("itsup-apply.service", "itsup-bringup.service")
STATE_DIRECTORY_DIRECTIVE = "StateDirectory=itsup"
STAMP_COMMAND = "ExecStartPost=/bin/sh -c 'touch \"$STATE_DIRECTORY/apply-success\"'"

INSTALL_SCRIPT = (REPO_ROOT / "bin" / "install-bringup.sh").read_text(encoding="utf-8")
UNINSTALL_SCRIPT = (REPO_ROOT / "bin" / "uninstall-runtime.sh").read_text(encoding="utf-8")
HEALTHCHECK_SCRIPT = (REPO_ROOT / "bin" / "pi-healthcheck.sh").read_text(encoding="utf-8")


def _render(unit_name: str, dest_dir: Path) -> Path:
    template = (SYSTEMD_DIR / unit_name).read_text(encoding="utf-8")
    rendered = (
        template.replace("{{USER}}", "testuser")
        .replace("{{GROUP}}", "testgroup")
        .replace("{{ROOT}}", "/opt/itsup")
        .replace("{{HOME}}", "/home/testuser")
    )
    dest = dest_dir / unit_name
    dest.write_text(rendered, encoding="utf-8")
    return dest


def test_every_covered_unit_declares_the_failure_hook() -> None:
    for unit_name in COVERED_UNITS:
        content = (SYSTEMD_DIR / unit_name).read_text(encoding="utf-8")
        assert ALERT_ON_FAILURE in content, unit_name


def test_alert_template_is_referenced_only_by_onfailure() -> None:
    """UC-OFA3's exclusivity proof: no covered unit — or the template itself —
    reaches the composer through anything but the supervisor's failure hook."""
    for unit_name in (*COVERED_UNITS, ALERT_TEMPLATE):
        content = (SYSTEMD_DIR / unit_name).read_text(encoding="utf-8")
        referencing_lines = [line for line in content.splitlines() if ALERT_REFERENCE_MARKER in line]
        for line in referencing_lines:
            assert line.strip().startswith(ON_FAILURE_PREFIX), f"{unit_name}: {line!r}"

    alert_template_content = (SYSTEMD_DIR / ALERT_TEMPLATE).read_text(encoding="utf-8")
    assert ON_FAILURE_PREFIX not in alert_template_content


@pytest.mark.skipif(shutil.which("systemd-analyze") is None, reason="systemd-analyze not available on this host")
def test_rendered_units_pass_systemd_analyze_verify(tmp_path: Path) -> None:
    rendered_paths = [_render(name, tmp_path) for name in (*COVERED_UNITS, ALERT_TEMPLATE)]
    result = subprocess.run(
        ["systemd-analyze", "verify", *(str(p) for p in rendered_paths)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_apply_and_bringup_stamp_success_into_state_directory() -> None:
    for unit_name in STAMPED_UNITS:
        content = (SYSTEMD_DIR / unit_name).read_text(encoding="utf-8")
        assert STATE_DIRECTORY_DIRECTIVE in content, unit_name
        assert STAMP_COMMAND in content, unit_name


def test_installer_registers_the_alert_unit_and_journal_group() -> None:
    assert ALERT_UNIT_ARRAY_ENTRY in INSTALL_SCRIPT
    assert SYSTEMD_JOURNAL_GROUP in INSTALL_SCRIPT


def test_uninstaller_removes_the_alert_unit() -> None:
    assert ALERT_UNIT_ARRAY_ENTRY in UNINSTALL_SCRIPT


def test_healthcheck_deadman_invocation_cannot_abort_the_script() -> None:
    collapsed = " ".join(HEALTHCHECK_SCRIPT.replace("\\\n", " ").split())
    assert DEADMAN_GUARD_PATTERN in collapsed
