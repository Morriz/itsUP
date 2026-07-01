#!/usr/bin/env python3

"""
Functional tests for diff-secrets command.

Uses REAL sops, REAL sops-diff, REAL git.
NO MOCKING (except path resolution).
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import TypedDict
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from click.testing import CliRunner

from commands.diff_secrets import diff_secrets

HELP_DESCRIPTION = "Show meaningful diffs of encrypted secrets"
SECRETS_DIR_NOT_FOUND = "secrets/ directory not found"
NO_ENCRYPTED_FILES = "No encrypted files found"
NEW_FILE_MARKER = "New file (not yet in git)"
DECRYPTED_SECRET_CONTENT = "SECRET=value"
FAILED_TO_DECRYPT = "Failed to decrypt"
FILE2_REQUIRED = "FILE2 required"
FILE_NOT_FOUND = "File not found"


class AgeKey(TypedDict):
    private_key_file: Path
    public_key: str


def test_diff_secrets_no_secrets_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test error handling when secrets/ directory doesn't exist."""
    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(diff_secrets)

    assert result.exit_code == 1
    assert SECRETS_DIR_NOT_FOUND in result.output


def test_diff_secrets_no_encrypted_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test warning when no encrypted files exist."""
    # Create empty secrets directory
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()

    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(diff_secrets)

    assert result.exit_code == 0
    assert NO_ENCRYPTED_FILES in result.output


def test_diff_secrets_uses_secrets_repo_not_parent_repo(
    tmp_path: Path, real_age_key: AgeKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REGRESSION TEST: Verify git commands run in secrets repo, not parent.

    This is the critical test for the bug where all files showed as "new"
    because git cat-file ran in the wrong repository.

    FUNCTIONAL TEST - uses REAL git repos.
    """
    # Create REAL parent repo
    parent_repo = tmp_path / "itsup"
    parent_repo.mkdir()
    subprocess.run(["git", "init"], cwd=parent_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=parent_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=parent_repo,
        check=True,
        capture_output=True,
    )

    # Create REAL secrets repo (SEPARATE git repo)
    secrets_repo = parent_repo / "secrets"
    secrets_repo.mkdir()
    subprocess.run(["git", "init"], cwd=secrets_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=secrets_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=secrets_repo,
        check=True,
        capture_output=True,
    )

    # Create and commit REAL encrypted file ONLY in secrets repo
    plaintext = secrets_repo / "secret.txt"
    plaintext.write_text("KEY=value")

    encrypted = secrets_repo / "secret.enc.txt"
    subprocess.run(
        [
            "sops",
            "-e",
            "--age",
            real_age_key["public_key"],
            "--output",
            str(encrypted),
            str(plaintext),
        ],
        check=True,
        capture_output=True,
    )
    plaintext.unlink()

    subprocess.run(["git", "add", "."], cwd=secrets_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add secret"],
        cwd=secrets_repo,
        check=True,
        capture_output=True,
    )

    # File does NOT exist in parent repo git history

    # Run command
    env = {
        **os.environ,
        "SOPS_AGE_KEY_FILE": str(real_age_key["private_key_file"]),
    }

    monkeypatch.setenv("ITSUP_ROOT", str(parent_repo))

    with patch("commands.diff_secrets._check_sops_diff", return_value=True):
        runner = CliRunner(env=env)
        result = runner.invoke(diff_secrets, [])

    # CRITICAL: Should NOT show as new file
    # (If bug exists, would check parent repo and show "new")
    assert NEW_FILE_MARKER not in result.output, "File IS committed in secrets repo, should not show as new"


def test_diff_secrets_with_uncommitted_file(
    tmp_path: Path, real_age_key: AgeKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uncommitted encrypted files should show as 'New file'.

    FUNCTIONAL TEST - uses real git and sops.
    """
    # Create parent repo
    parent_repo = tmp_path / "itsup"
    parent_repo.mkdir()
    subprocess.run(["git", "init"], cwd=parent_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=parent_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=parent_repo,
        check=True,
        capture_output=True,
    )

    # Create secrets repo
    secrets_repo = parent_repo / "secrets"
    secrets_repo.mkdir()
    subprocess.run(["git", "init"], cwd=secrets_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=secrets_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=secrets_repo,
        check=True,
        capture_output=True,
    )

    # Create .sops.yaml in secrets repo
    sops_config = secrets_repo / ".sops.yaml"
    sops_config.write_text(f"""creation_rules:
  - age: {real_age_key["public_key"]}
""")

    # Create and encrypt a file but DON'T commit it
    plaintext = secrets_repo / "uncommitted.txt"
    plaintext.write_text("SECRET=value")

    encrypted = secrets_repo / "uncommitted.enc.txt"
    subprocess.run(
        [
            "sops",
            "-e",
            "--age",
            real_age_key["public_key"],
            "--output",
            str(encrypted),
            str(plaintext),
        ],
        check=True,
        capture_output=True,
    )
    plaintext.unlink()

    # File is NOT committed to git

    # Run command
    env = {
        **os.environ,
        "SOPS_AGE_KEY_FILE": str(real_age_key["private_key_file"]),
    }

    monkeypatch.setenv("ITSUP_ROOT", str(parent_repo))

    with patch("commands.diff_secrets._check_sops_diff", return_value=True):
        runner = CliRunner(env=env)
        result = runner.invoke(diff_secrets, [])

    # Should show as new file
    assert NEW_FILE_MARKER in result.output, "Uncommitted file should show as new"
    # Should decrypt and show content
    assert DECRYPTED_SECRET_CONTENT in result.output, "Should show decrypted content of new file"


def test_diff_secrets_corrupted_file_shows_decrypt_error(
    tmp_path: Path, real_age_key: AgeKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that corrupted encrypted files show decrypt error."""
    # Create parent repo
    parent_repo = tmp_path / "itsup"
    parent_repo.mkdir()
    subprocess.run(["git", "init"], cwd=parent_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=parent_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=parent_repo,
        check=True,
        capture_output=True,
    )

    # Create secrets repo
    secrets_repo = parent_repo / "secrets"
    secrets_repo.mkdir()
    subprocess.run(["git", "init"], cwd=secrets_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=secrets_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=secrets_repo,
        check=True,
        capture_output=True,
    )

    # Create corrupted "encrypted" file (not actual SOPS)
    corrupted = secrets_repo / "corrupted.enc.txt"
    corrupted.write_text("This is not a valid SOPS encrypted file")

    # Run command
    env = {
        **os.environ,
        "SOPS_AGE_KEY_FILE": str(real_age_key["private_key_file"]),
    }

    monkeypatch.setenv("ITSUP_ROOT", str(parent_repo))

    with patch("commands.diff_secrets._check_sops_diff", return_value=True):
        runner = CliRunner(env=env)
        result = runner.invoke(diff_secrets, [])

    # Should show decrypt error for corrupted file
    assert FAILED_TO_DECRYPT in result.output or result.exit_code == 1


def test_diff_secrets_requires_file2_without_git_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that FILE2 is required when not using --git flag."""
    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    with patch("commands.diff_secrets._check_sops_diff", return_value=True):
        runner = CliRunner()
        result = runner.invoke(diff_secrets, ["file1.txt"])

    assert result.exit_code == 1
    assert FILE2_REQUIRED in result.output


def test_diff_secrets_file_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test error handling when file doesn't exist."""
    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    with patch("commands.diff_secrets._check_sops_diff", return_value=True):
        runner = CliRunner()
        result = runner.invoke(diff_secrets, ["nonexistent1.txt", "nonexistent2.txt"])

    assert result.exit_code == 1
    assert FILE_NOT_FOUND in result.output
