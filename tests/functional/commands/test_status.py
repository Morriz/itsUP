#!/usr/bin/env python3

"""
Functional tests for 'itsup status' command.

Tests git status reporting for projects/ and secrets/ repos.
Uses REAL git commands.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from click.testing import CliRunner

from commands.status import status


def test_status_both_repos_clean(tmp_path):
    """Test status when both repos are clean."""
    # Create projects and secrets as git repos
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    subprocess.run(["git", "init"], cwd=projects_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=projects_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=projects_dir, check=True, capture_output=True)

    # Create and commit a file so repo is clean
    (projects_dir / "test.txt").write_text("test")
    subprocess.run(["git", "add", "."], cwd=projects_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=projects_dir, check=True, capture_output=True)

    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    subprocess.run(["git", "init"], cwd=secrets_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=secrets_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=secrets_dir, check=True, capture_output=True)

    (secrets_dir / "secret.txt").write_text("secret")
    subprocess.run(["git", "add", "."], cwd=secrets_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=secrets_dir, check=True, capture_output=True)

    # Create commands directory for __file__ mocking
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()

    with patch("commands.status.__file__", str(commands_dir / "status.py")):
        runner = CliRunner()
        result = runner.invoke(status, [])

    assert result.exit_code == 0
    assert "clean" in result.output.lower()
    assert "projects/ repo" in result.output
    assert "secrets/ repo" in result.output


def test_status_projects_repo_dirty(tmp_path):
    """Test status when projects/ has uncommitted changes."""
    # Create projects repo with uncommitted file
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    subprocess.run(["git", "init"], cwd=projects_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=projects_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=projects_dir, check=True, capture_output=True)

    # Add uncommitted file
    (projects_dir / "uncommitted.txt").write_text("new file")

    # Clean secrets repo
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    subprocess.run(["git", "init"], cwd=secrets_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=secrets_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=secrets_dir, check=True, capture_output=True)

    (secrets_dir / "file.txt").write_text("content")
    subprocess.run(["git", "add", "."], cwd=secrets_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=secrets_dir, check=True, capture_output=True)

    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()

    with patch("commands.status.__file__", str(commands_dir / "status.py")):
        runner = CliRunner()
        result = runner.invoke(status, [])

    assert result.exit_code == 0
    assert "has changes" in result.output or "uncommitted" in result.output.lower()
    assert "projects/" in result.output


def test_status_both_repos_dirty(tmp_path):
    """Test status when both repos have changes."""
    # Create both repos with uncommitted files
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    subprocess.run(["git", "init"], cwd=projects_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=projects_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=projects_dir, check=True, capture_output=True)
    (projects_dir / "uncommitted.txt").write_text("new")

    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    subprocess.run(["git", "init"], cwd=secrets_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=secrets_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=secrets_dir, check=True, capture_output=True)
    (secrets_dir / "uncommitted.txt").write_text("new")

    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()

    with patch("commands.status.__file__", str(commands_dir / "status.py")):
        runner = CliRunner()
        result = runner.invoke(status, [])

    assert result.exit_code == 0
    assert "has changes" in result.output or "uncommitted" in result.output.lower()


def test_status_missing_projects_directory(tmp_path):
    """Test status when projects/ doesn't exist."""
    # Only create secrets repo
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    subprocess.run(["git", "init"], cwd=secrets_dir, check=True, capture_output=True)

    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()

    with patch("commands.status.__file__", str(commands_dir / "status.py")):
        runner = CliRunner()
        result = runner.invoke(status, [])

    # Command fails when directory doesn't exist
    assert result.exit_code == 1


def test_status_not_git_repos(tmp_path):
    """Test status when directories exist but aren't git repos."""
    # Create directories but don't init git
    (tmp_path / "projects").mkdir()
    (tmp_path / "secrets").mkdir()

    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()

    with patch("commands.status.__file__", str(commands_dir / "status.py")):
        runner = CliRunner()
        result = runner.invoke(status, [])

    # Should handle error gracefully
    assert result.exit_code == 0
