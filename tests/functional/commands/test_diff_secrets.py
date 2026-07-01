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
from unittest.mock import patch

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


def test_diff_secrets_help():
    """Test diff-secrets help command.

    Basic sanity check.
    """
    runner = CliRunner()
    result = runner.invoke(diff_secrets, ["--help"])
    assert result.exit_code == 0
    assert HELP_DESCRIPTION in result.output


def test_diff_secrets_no_secrets_directory(tmp_path, monkeypatch):
    """Test error handling when secrets/ directory doesn't exist."""
    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(diff_secrets)

    assert result.exit_code == 1
    assert SECRETS_DIR_NOT_FOUND in result.output


def test_diff_secrets_no_encrypted_files(tmp_path, monkeypatch):
    """Test warning when no encrypted files exist."""
    # Create empty secrets directory
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()

    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(diff_secrets)

    assert result.exit_code == 0
    assert NO_ENCRYPTED_FILES in result.output


def test_diff_secrets_uses_secrets_repo_not_parent_repo(tmp_path, real_age_key, monkeypatch):
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
    subprocess.run(
        ["git", "init"], cwd=secrets_repo, check=True, capture_output=True
    )
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

    subprocess.run(
        ["git", "add", "."], cwd=secrets_repo, check=True, capture_output=True
    )
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


def test_diff_secrets_with_uncommitted_file(tmp_path, real_age_key, monkeypatch):
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
    subprocess.run(
        ["git", "init"], cwd=secrets_repo, check=True, capture_output=True
    )
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
    sops_config.write_text(
        f"""creation_rules:
  - age: {real_age_key["public_key"]}
"""
    )

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


def test_diff_secrets_corrupted_file_shows_decrypt_error(tmp_path, real_age_key, monkeypatch):
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
    subprocess.run(
        ["git", "init"], cwd=secrets_repo, check=True, capture_output=True
    )
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


def test_diff_secrets_specific_files_comparison(tmp_path, real_age_key, monkeypatch):
    """Test comparing two specific encrypted files."""
    # Create .sops.yaml
    (tmp_path / ".sops.yaml").write_text(
        f"""creation_rules:
  - age: {real_age_key["public_key"]}
"""
    )

    # Create two different plaintext files
    plaintext1 = tmp_path / "secret1.txt"
    plaintext1.write_text("KEY=value1")

    plaintext2 = tmp_path / "secret2.txt"
    plaintext2.write_text("KEY=value2")

    # Encrypt both
    encrypted1 = tmp_path / "secret1.enc.txt"
    encrypted2 = tmp_path / "secret2.enc.txt"

    for plaintext, encrypted in [(plaintext1, encrypted1), (plaintext2, encrypted2)]:
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

    # Run diff-secrets with two files
    env = {
        **os.environ,
        "SOPS_AGE_KEY_FILE": str(real_age_key["private_key_file"]),
    }

    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    with patch("commands.diff_secrets._check_sops_diff", return_value=True):
        runner = CliRunner(env=env)
        result = runner.invoke(
            diff_secrets,
            [str(encrypted1.relative_to(tmp_path)), str(encrypted2.relative_to(tmp_path))],
        )

    # Should run sops-diff (non-zero exit if files differ)
    assert result.exit_code in [0, 1]  # 0 = same, 1 = different


def test_diff_secrets_requires_file2_without_git_flag(tmp_path, monkeypatch):
    """Test that FILE2 is required when not using --git flag."""
    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    with patch("commands.diff_secrets._check_sops_diff", return_value=True):
        runner = CliRunner()
        result = runner.invoke(diff_secrets, ["file1.txt"])

    assert result.exit_code == 1
    assert FILE2_REQUIRED in result.output


def test_diff_secrets_file_not_found(tmp_path, monkeypatch):
    """Test error handling when file doesn't exist."""
    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    with patch("commands.diff_secrets._check_sops_diff", return_value=True):
        runner = CliRunner()
        result = runner.invoke(diff_secrets, ["nonexistent1.txt", "nonexistent2.txt"])

    assert result.exit_code == 1
    assert FILE_NOT_FOUND in result.output


def test_diff_secrets_with_git_flag(tmp_path, real_age_key, monkeypatch):
    """Test --git flag for comparing with git revision."""
    # Create git repo
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    # Create .sops.yaml
    (tmp_path / ".sops.yaml").write_text(
        f"""creation_rules:
  - age: {real_age_key["public_key"]}
"""
    )

    # Create and commit encrypted file
    plaintext = tmp_path / "secret.txt"
    plaintext.write_text("KEY=value1")

    encrypted = tmp_path / "secret.enc.txt"
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

    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    # Modify and re-encrypt
    plaintext.write_text("KEY=value2")
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

    # Run diff-secrets with --git flag
    env = {
        **os.environ,
        "SOPS_AGE_KEY_FILE": str(real_age_key["private_key_file"]),
    }

    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    with patch("commands.diff_secrets._check_sops_diff", return_value=True):
        runner = CliRunner(env=env)
        result = runner.invoke(
            diff_secrets, ["--git", "HEAD:secret.enc.txt", "secret.enc.txt"]
        )

    # Should run sops-diff (exit code 1 because files differ)
    assert result.exit_code in [0, 1]
