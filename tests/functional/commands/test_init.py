#!/usr/bin/env python3

"""
Functional tests for 'itsup init' command.

Tests project initialization, repo cloning, sample file copying.
Uses REAL file operations and git.
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from click.testing import CliRunner

from commands.init import init

MUST_BE_RUN_FROM_ROOT = "Must be run from itsUP project root"
PROJECTS_ALREADY_EXISTS = "projects/ already exists"
SECRETS_ALREADY_EXISTS = "secrets/ already exists"
ENV_VAR_LINE = "ENV_VAR=test_value"
ENV_ALREADY_EXISTS = ".env already exists"
EXISTING_ENV_CONTENT = "EXISTING=value"
REQUIRED_SOURCE_MISSING = "Required sample source is missing"


def _make_itsup_samples(root: Path) -> None:
    """Build a minimal valid itsUP samples/ template tree under an ITSUP_ROOT."""
    projects = root / "samples" / "projects"
    projects.mkdir(parents=True)
    (projects / "itsup.yml").write_text("routerIP: 1.2.3.4\n")
    (projects / "traefik.yml").write_text("log:\n  level: INFO\n")
    (projects / "middlewares.yml").write_text("http: {}\n")
    example = projects / "example-project"
    example.mkdir()
    (example / "docker-compose.yml").write_text("services: {}\n")

    secrets = root / "samples" / "secrets"
    secrets.mkdir(parents=True)
    (secrets / "itsup.txt").write_text("TRAEFIK_ADMIN=changeme\n")

    (root / "samples" / ".env").write_text(f"{ENV_VAR_LINE}\n")


def _make_existing_repos(root: Path) -> None:
    """Create projects/ and secrets/ as pre-existing git repos so init skips cloning."""
    for name in ("projects", "secrets"):
        d = root / name
        d.mkdir()
        subprocess.run(["git", "init"], cwd=d, check=True, capture_output=True)


@pytest.mark.functional
def test_init_validates_project_structure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """init refuses a resolved root that is not an itsUP checkout (no marker file)."""
    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    result = CliRunner().invoke(init, [])

    assert result.exit_code == 1
    assert MUST_BE_RUN_FROM_ROOT in result.output


@pytest.mark.functional
def test_init_refuses_when_marker_is_a_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A directory named samples/projects/itsup.yml is not a file marker; init refuses."""
    (tmp_path / "samples" / "projects" / "itsup.yml").mkdir(parents=True)
    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    result = CliRunner().invoke(init, [])

    assert result.exit_code == 1
    assert MUST_BE_RUN_FROM_ROOT in result.output


@pytest.mark.functional
def test_init_with_existing_projects_and_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test init when projects/ and secrets/ already exist."""
    _make_itsup_samples(tmp_path)
    _make_existing_repos(tmp_path)

    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    result = CliRunner().invoke(init, input="\n\n\n")

    assert result.exit_code == 0
    assert PROJECTS_ALREADY_EXISTS in result.output
    assert SECRETS_ALREADY_EXISTS in result.output


@pytest.mark.functional
def test_init_seeds_projects_and_secrets_by_mirroring(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """init seeds .env and every samples/projects and samples/secrets entry."""
    _make_itsup_samples(tmp_path)
    _make_existing_repos(tmp_path)

    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    result = CliRunner().invoke(init, input="\n\n\n")

    assert result.exit_code == 0
    assert (tmp_path / ".env").exists()
    for name in ("itsup.yml", "traefik.yml", "middlewares.yml", "example-project"):
        assert (tmp_path / "projects" / name).exists(), f"projects/{name} not seeded"
    assert (tmp_path / "secrets" / "itsup.txt").exists()


@pytest.mark.functional
def test_init_creates_env_file_from_sample(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that init copies samples/.env to .env if missing."""
    _make_itsup_samples(tmp_path)
    _make_existing_repos(tmp_path)

    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    result = CliRunner().invoke(init, input="\n\n\n")

    assert result.exit_code == 0

    env_file = tmp_path / ".env"
    assert env_file.exists()
    assert ENV_VAR_LINE in env_file.read_text()


@pytest.mark.functional
def test_init_skips_existing_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """init never overwrites an existing destination."""
    _make_itsup_samples(tmp_path)
    _make_existing_repos(tmp_path)

    env_file = tmp_path / ".env"
    env_file.write_text(EXISTING_ENV_CONTENT)

    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    result = CliRunner().invoke(init, input="\n\n\n")

    assert result.exit_code == 0
    assert env_file.read_text() == EXISTING_ENV_CONTENT
    assert ENV_ALREADY_EXISTS in result.output


@pytest.mark.functional
def test_init_fails_loudly_on_missing_required_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A checkout that passes the guard but lacks a required sample source fails loudly."""
    _make_itsup_samples(tmp_path)
    _make_existing_repos(tmp_path)
    (tmp_path / "samples" / ".env").unlink()

    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    result = CliRunner().invoke(init, input="\n\n\n")

    assert result.exit_code == 1
    assert REQUIRED_SOURCE_MISSING in result.output
