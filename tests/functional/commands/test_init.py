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

from commands.init import MISSING_SAMPLE_MESSAGE, NOT_ITSUP_ROOT_MESSAGE, init

SPEC_ID = "project/spec/feature/cli/init-project-setup"

ENV_CONTENT = "ENV_VAR=test_value\n"
EXISTING_ENV_CONTENT = "EXISTING=value"
# Entries no hardcoded manifest would list — prove seeding mirrors the tree.
UNLISTED_PROJECT = "unlisted-project.yml"
UNLISTED_SECRET = "unlisted-secret.txt"


def _make_itsup_samples(root: Path) -> None:
    """Build a minimal valid itsUP samples/ template tree under an ITSUP_ROOT."""
    projects = root / "samples" / "projects"
    projects.mkdir(parents=True)
    (projects / "itsup.yml").write_text("routerIP: 1.2.3.4\n")
    (projects / "traefik.yml").write_text("log:\n  level: INFO\n")
    (projects / "middlewares.yml").write_text("http: {}\n")
    (projects / UNLISTED_PROJECT).write_text("services: {}\n")
    example = projects / "example-project"
    example.mkdir()
    (example / "docker-compose.yml").write_text("services: {}\n")

    secrets = root / "samples" / "secrets"
    secrets.mkdir(parents=True)
    (secrets / "itsup.txt").write_text("TRAEFIK_ADMIN=changeme\n")
    (secrets / UNLISTED_SECRET).write_text("EXTRA=changeme\n")

    (root / "samples" / ".env").write_text(ENV_CONTENT)


def _make_existing_repos(root: Path) -> None:
    """Create projects/ and secrets/ as pre-existing git repos so init skips cloning."""
    for name in ("projects", "secrets"):
        d = root / name
        d.mkdir()
        subprocess.run(["git", "init"], cwd=d, check=True, capture_output=True)


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-IPS1")
def test_init_validates_project_structure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """UC-IPS1: init refuses a resolved root without the marker file."""
    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    result = CliRunner().invoke(init, [])

    assert result.exit_code == 1
    assert NOT_ITSUP_ROOT_MESSAGE in result.output


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-IPS1")
def test_init_refuses_when_marker_is_a_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """UC-IPS1: a directory named samples/projects/itsup.yml is not a file marker."""
    (tmp_path / "samples" / "projects" / "itsup.yml").mkdir(parents=True)
    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    result = CliRunner().invoke(init, [])

    assert result.exit_code == 1
    assert NOT_ITSUP_ROOT_MESSAGE in result.output


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-IPS2")
def test_init_with_existing_projects_and_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """UC-IPS2: init reuses existing repos and still seeds them from samples."""
    _make_itsup_samples(tmp_path)
    _make_existing_repos(tmp_path)

    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    result = CliRunner().invoke(init, input="\n\n\n")

    assert result.exit_code == 0
    assert (tmp_path / "projects" / "itsup.yml").exists()
    assert (tmp_path / "secrets" / "itsup.txt").exists()


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-IPS2")
def test_init_seeds_projects_and_secrets_by_mirroring(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """UC-IPS2: init seeds .env and every samples/projects and samples/secrets entry."""
    _make_itsup_samples(tmp_path)
    _make_existing_repos(tmp_path)

    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    result = CliRunner().invoke(init, input="\n\n\n")

    assert result.exit_code == 0
    assert (tmp_path / ".env").exists()
    for name in ("itsup.yml", "traefik.yml", "middlewares.yml", "example-project"):
        assert (tmp_path / "projects" / name).exists(), f"projects/{name} not seeded"
    assert (tmp_path / "secrets" / "itsup.txt").exists()
    # Entries no hardcoded manifest would name are seeded too — the mirror tracks
    # the tree, so a reversion to a static list would leave these behind.
    assert (tmp_path / "projects" / UNLISTED_PROJECT).exists()
    assert (tmp_path / "secrets" / UNLISTED_SECRET).exists()


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-IPS2")
def test_init_creates_env_file_from_sample(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """UC-IPS2: the seeded .env is a faithful copy of samples/.env."""
    _make_itsup_samples(tmp_path)
    _make_existing_repos(tmp_path)

    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    result = CliRunner().invoke(init, input="\n\n\n")

    assert result.exit_code == 0
    env_file = tmp_path / ".env"
    assert env_file.read_text() == (tmp_path / "samples" / ".env").read_text()


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-IPS3")
def test_init_skips_existing_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """UC-IPS3: init never overwrites an existing destination."""
    _make_itsup_samples(tmp_path)
    _make_existing_repos(tmp_path)

    env_file = tmp_path / ".env"
    env_file.write_text(EXISTING_ENV_CONTENT)

    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    result = CliRunner().invoke(init, input="\n\n\n")

    assert result.exit_code == 0
    assert env_file.read_text() == EXISTING_ENV_CONTENT


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-IPS4")
def test_init_fails_loudly_on_missing_required_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """UC-IPS4: a checkout that passes the guard but lacks a required sample source fails loudly."""
    _make_itsup_samples(tmp_path)
    _make_existing_repos(tmp_path)
    (tmp_path / "samples" / ".env").unlink()

    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    result = CliRunner().invoke(init, input="\n\n\n")

    assert result.exit_code == 1
    assert MISSING_SAMPLE_MESSAGE in result.output
