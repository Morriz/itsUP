#!/usr/bin/env python3

"""Regression coverage for UC-CV1: itsup validate rejects Compose-invalid config.

Entry surface: the real CLI (``itsup.cli`` ``validate`` command), invoked
in-process via click's ``CliRunner`` with ``ITSUP_ROOT`` pointed at a scratch
install root — the same real-boundary shape as
``tests/functional/test_cli_cwd_independence.py``. The real ``docker compose``
binary is exercised for real; the test skips when it is unavailable, following
the precedent in ``tests/functional/bin/test_write_artifacts.py``.
"""

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from itsup.cli import cli
from lib.data import COMPOSE_SCHEMA_FAILURE_PREFIX

SPEC_ID = "project/spec/feature/deployment/config-validation"


@pytest.fixture(autouse=True)
def _skip_without_docker() -> None:
    """Skip the module's tests when the docker CLI is unavailable (e.g. minimal CI)."""
    try:
        subprocess.run(["docker", "compose", "version"], capture_output=True, timeout=10, check=False)
    except FileNotFoundError:
        pytest.skip("Docker not available - skipping compose schema validation")


@pytest.fixture(name="scratch_root")
def scratch_root_fixture(tmp_path: Path) -> Path:
    """A complete install tree: pyproject + schema-matched itsup.yml + secrets/.

    Mirrors ``install_root_fixture`` in ``test_cli_cwd_independence.py`` — the
    real CLI's ``guard_schema_version`` reads both files, so they must satisfy
    the real schema-version check.
    """
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "2.1.1"\n')
    projects = tmp_path / "projects"
    projects.mkdir()
    (projects / "itsup.yml").write_text('schemaVersion: "2.1.0"\nrouterIP: 192.168.1.1\n')
    (tmp_path / "secrets").mkdir()
    return tmp_path


def _write_project(scratch_root: Path, name: str, compose_yaml: str) -> None:
    project = scratch_root / "projects" / name
    project.mkdir(parents=True)
    (project / "docker-compose.yml").write_text(compose_yaml)
    (project / "itsup-project.yml").write_text("enabled: true\n")


def _validate(scratch_root: Path, project: str) -> tuple[int, str]:
    """Run the real CLI's validate command in-process, return combined output."""
    runner = CliRunner()
    result = runner.invoke(cli, ["validate", project], env={"ITSUP_ROOT": str(scratch_root)})
    return result.exit_code, result.output


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-CV1")
def test_reported_healthcheck_shape_is_rejected(scratch_root: Path) -> None:
    """UC-CV1: the exact reported healthcheck.test shape is YAML-valid but Compose-invalid."""
    _write_project(
        scratch_root,
        "repro",
        "services:\n"
        "  repro-frontend:\n"
        "    image: nginx:alpine\n"
        "    healthcheck:\n"
        "      test:\n"
        "        - CMD-SHELL\n"
        '        - curl -fsS -H "Host: $$HEALTHCHECK_SITE" http://localhost:8080/api/method/ping || exit 1\n',
    )

    exit_code, output = _validate(scratch_root, "repro")

    assert exit_code != 0
    assert COMPOSE_SCHEMA_FAILURE_PREFIX in output


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-CV1")
def test_falsy_compose_document_is_still_schema_checked(scratch_root: Path) -> None:
    """UC-CV1: a present but comments-only docker-compose.yml is rejected, not skipped."""
    _write_project(scratch_root, "empty-compose", "# just a comment\n")

    exit_code, output = _validate(scratch_root, "empty-compose")

    assert exit_code != 0
    assert COMPOSE_SCHEMA_FAILURE_PREFIX in output


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-CV1")
def test_required_variable_without_secret_still_passes(scratch_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """UC-CV1 acceptance contrast: a Compose-valid file with an unset required
    variable and no decryptable secret still passes — the schema verdict is
    interpolation-independent, so valid secret-backed files pass on keyless
    runs-anywhere machines."""
    # bin/write_artifacts.py calls load_dotenv() at import, which can pull
    # API_KEY in from a real .env found by walking up from this worktree;
    # scrub it so the Given ("API_KEY absent") holds regardless of ambient env.
    monkeypatch.delenv("API_KEY", raising=False)
    _write_project(
        scratch_root,
        "needs-secret",
        "services:\n"
        "  web:\n"
        "    image: nginx:alpine\n"
        "    environment:\n"
        "      API_KEY: ${API_KEY:?required}\n",
    )

    exit_code, output = _validate(scratch_root, "needs-secret")

    assert exit_code == 0
    assert COMPOSE_SCHEMA_FAILURE_PREFIX not in output
