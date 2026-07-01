#!/usr/bin/env python3

"""Process-tier acceptance: itsup runs cwd-independently.

Invokes the REAL ``bin/itsup`` shim as an OS subprocess from ``/`` and from an
unrelated directory, proving data resolution follows ``ITSUP_ROOT`` (or the
package location) and never the caller's cwd. This is the acceptance criterion
for ``project/design/itsup-cli`` invariant 2, exercised across representative
commands (a data-read command, a root-derived-path command), the
package-derived ``root()`` branch, and the fail-closed branch.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SHIM = REPO_ROOT / "bin" / "itsup"
CONSOLE_SCRIPT = REPO_ROOT / ".venv" / "bin" / "itsup"

sys.path.insert(0, str(REPO_ROOT))

ALL_PROJECTS_VALID = "All projects valid"
GIT_STATUS_HEADER = "Git Status"
VERSION_LABEL = "version"
ITSUP_ROOT_ENV = "ITSUP_ROOT"
DECOY_PROJECT = "broken-app"
AVAILABLE_LOG = "access"


def _write_valid_project(projects_dir: Path, name: str, domain: str) -> None:
    """Create a project that ``itsup validate`` accepts."""
    project = projects_dir / name
    project.mkdir(parents=True)
    (project / "docker-compose.yml").write_text(
        'services:\n  web:\n    image: nginx:latest\n    ports:\n      - "8080:80"\n'
    )
    (project / "ingress.yml").write_text(
        "enabled: true\n" "ingress:\n" f"  - service: web\n    domain: {domain}\n    port: 80\n    router: http\n"
    )


@pytest.fixture
def valid_root(tmp_path: Path) -> Path:
    """A complete install tree: pyproject + schema-matched itsup.yml + one valid project.

    The subprocess runs the real CLI (no in-process monkeypatching), so the tree
    must satisfy the real schema-version check: ``get_app_version`` reads
    ``pyproject.toml`` and ``get_schema_version`` reads ``projects/itsup.yml`` —
    equal versions keep ``check_schema_version`` silent.
    """
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "2.0.0"\n')
    projects = tmp_path / "projects"
    projects.mkdir()
    (projects / "itsup.yml").write_text('schemaVersion: "2.0.0"\nrouterIP: 192.168.1.1\n')
    (tmp_path / "secrets").mkdir()
    _write_valid_project(projects, "good-app", "good.example.com")
    return tmp_path


def _run(args: list[str], cwd: str, itsup_root: Path | None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if itsup_root is not None:
        env["ITSUP_ROOT"] = str(itsup_root)
    else:
        env.pop("ITSUP_ROOT", None)
    return subprocess.run(
        [sys.executable, str(SHIM), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_validate_reads_itsup_root_from_filesystem_root(valid_root: Path) -> None:
    """A data-read command run from / resolves projects/ under ITSUP_ROOT, not cwd."""
    result = _run(["validate"], cwd="/", itsup_root=valid_root)

    assert result.returncode == 0, result.stderr
    assert ALL_PROJECTS_VALID in result.stdout


def test_validate_ignores_cwd_projects(valid_root: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    """A decoy projects/ in the cwd is ignored; ITSUP_ROOT wins."""
    decoy_cwd = tmp_path_factory.mktemp("decoy")
    # A broken project in the cwd that would fail validation if it were read.
    broken = decoy_cwd / "projects" / "broken-app"
    broken.mkdir(parents=True)
    (broken / "docker-compose.yml").write_text("not: [valid, compose")

    result = _run(["validate"], cwd=str(decoy_cwd), itsup_root=valid_root)

    assert result.returncode == 0, result.stderr
    assert ALL_PROJECTS_VALID in result.stdout
    assert DECOY_PROJECT not in result.stdout


def test_root_derived_command_runs_from_unrelated_dir(
    valid_root: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """A root-derived-path command (status) resolves its repos under root(), runs from any cwd."""
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    result = _run(["status"], cwd=str(elsewhere), itsup_root=valid_root)

    assert result.returncode == 0, result.stderr
    assert GIT_STATUS_HEADER in result.stdout


def test_package_derived_root_when_env_unset() -> None:
    """With ITSUP_ROOT unset, root() derives the repo root from the package location."""
    result = _run(["--version"], cwd="/", itsup_root=None)

    assert result.returncode == 0, result.stderr
    assert VERSION_LABEL in result.stdout.lower()


def test_logs_resolves_logs_dir_under_root(valid_root: Path) -> None:
    """itsup logs lists log files from root()/logs, not the caller's cwd."""
    logs_dir = valid_root / "logs"
    logs_dir.mkdir()
    (logs_dir / f"{AVAILABLE_LOG}.log").write_text("{}\n")

    # A name that does not exist exits before the blocking `tail -F`, but the
    # "Available: …" list is read from root()/logs — empty if cwd were used.
    result = _run(["logs", "no-such-log"], cwd="/", itsup_root=valid_root)

    assert result.returncode == 1
    assert AVAILABLE_LOG in (result.stderr + result.stdout)


def test_fails_closed_on_missing_itsup_root(tmp_path: Path) -> None:
    """A non-existent ITSUP_ROOT fails closed with an error naming ITSUP_ROOT."""
    missing = tmp_path / "does-not-exist"
    result = _run(["--version"], cwd="/", itsup_root=missing)

    assert result.returncode != 0
    assert ITSUP_ROOT_ENV in (result.stderr + result.stdout)


def _run_console(args: list[str], cwd: str, itsup_root: Path) -> subprocess.CompletedProcess[str]:
    """Invoke the minted ``.venv/bin/itsup`` console-script directly (no python prefix).

    The console-script's shebang carries the venv interpreter, so it is exec'd as
    a standalone command — the canonical repo-local invocation, not the shim.
    """
    env = dict(os.environ)
    env["ITSUP_ROOT"] = str(itsup_root)
    return subprocess.run(
        [str(CONSOLE_SCRIPT), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.skipif(
    not CONSOLE_SCRIPT.exists(),
    reason="console-script absent — editable install not run (e.g. a bare CI venv)",
)
def test_console_script_runs_cwd_independently(
    valid_root: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """The canonical .venv/bin/itsup console-script reads ITSUP_ROOT from any cwd."""
    from_fs_root = _run_console(["validate"], cwd="/", itsup_root=valid_root)
    assert from_fs_root.returncode == 0, from_fs_root.stderr
    assert ALL_PROJECTS_VALID in from_fs_root.stdout

    elsewhere = tmp_path_factory.mktemp("elsewhere")
    from_elsewhere = _run_console(["validate"], cwd=str(elsewhere), itsup_root=valid_root)
    assert from_elsewhere.returncode == 0, from_elsewhere.stderr
    assert ALL_PROJECTS_VALID in from_elsewhere.stdout
