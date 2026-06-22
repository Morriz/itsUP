#!/usr/bin/env python3

"""
Functional tests for 'itsup init' command.

Tests project initialization, repo cloning, sample file copying.
Uses REAL file operations and git.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from click.testing import CliRunner

from commands.init import init

MUST_BE_RUN_FROM_ROOT = "Must be run from itsUP project root"
PROJECTS_ALREADY_EXISTS = "projects/ already exists"
SECRETS_ALREADY_EXISTS = "secrets/ already exists"
ENV_VAR_LINE = "ENV_VAR=test_value"
ENV_ALREADY_EXISTS = ".env already exists"
EXISTING_ENV_CONTENT = "EXISTING=value"


def test_init_validates_project_structure(tmp_path, monkeypatch):
    """Test that init validates it's run from correct directory."""
    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(init, [])

    assert result.exit_code == 1
    assert MUST_BE_RUN_FROM_ROOT in result.output


def test_init_with_existing_projects_and_secrets(tmp_path, monkeypatch):
    """Test init when projects/ and secrets/ already exist."""
    # Create full project structure
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "itsup").touch()

    samples_dir = tmp_path / "samples"
    samples_dir.mkdir()
    (samples_dir / "env").write_text("SAMPLE=value")

    # Create existing projects and secrets dirs (as git repos)
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    subprocess.run(["git", "init"], cwd=projects_dir, check=True, capture_output=True)

    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    subprocess.run(["git", "init"], cwd=secrets_dir, check=True, capture_output=True)

    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    runner = CliRunner()
    # Use input to simulate user pressing enter for all prompts
    result = runner.invoke(init, input="\n\n\n")

    assert result.exit_code == 0
    assert PROJECTS_ALREADY_EXISTS in result.output
    assert SECRETS_ALREADY_EXISTS in result.output


def test_init_creates_env_file_from_sample(tmp_path, monkeypatch):
    """Test that init copies samples/env to .env if missing."""
    # Create full project structure
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "itsup").touch()

    samples_dir = tmp_path / "samples"
    samples_dir.mkdir()
    (samples_dir / "env").write_text("ENV_VAR=test_value\n")

    # Create projects and secrets as git repos
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    subprocess.run(["git", "init"], cwd=projects_dir, check=True, capture_output=True)

    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    subprocess.run(["git", "init"], cwd=secrets_dir, check=True, capture_output=True)

    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(init, input="\n\n\n")

    assert result.exit_code == 0

    # Verify .env was created
    env_file = tmp_path / ".env"
    assert env_file.exists()
    assert ENV_VAR_LINE in env_file.read_text()


def test_init_skips_existing_env_file(tmp_path, monkeypatch):
    """Test that init doesn't overwrite existing .env file."""
    # Create full project structure
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "itsup").touch()

    samples_dir = tmp_path / "samples"
    samples_dir.mkdir()
    (samples_dir / "env").write_text("NEW_VAR=new")

    # Create existing .env
    env_file = tmp_path / ".env"
    env_file.write_text("EXISTING=value")

    # Create projects and secrets as git repos
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    subprocess.run(["git", "init"], cwd=projects_dir, check=True, capture_output=True)

    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    subprocess.run(["git", "init"], cwd=secrets_dir, check=True, capture_output=True)

    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(init, input="\n\n\n")

    assert result.exit_code == 0

    # Verify .env was NOT overwritten
    assert env_file.read_text() == EXISTING_ENV_CONTENT
    assert ENV_ALREADY_EXISTS in result.output
