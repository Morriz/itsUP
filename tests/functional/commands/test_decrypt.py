#!/usr/bin/env python3

"""
Functional tests for 'itsup decrypt' command.

Uses REAL sops binary for decryption.
NO MOCKING.
"""

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from click.testing import CliRunner

from commands.decrypt import decrypt

SECRETS_DIR_NOT_FOUND = "secrets/ directory not found"
FILE_NOT_FOUND = "File not found: secrets/nonexistent.enc.txt"
NO_ENCRYPTED_SECRETS = "No encrypted secrets found"
FAILED_TO_DECRYPT = "Failed to decrypt"


def test_decrypt_command_with_real_sops(tmp_path, real_age_key, monkeypatch):
    """Test 'itsup decrypt' command end-to-end.

    FUNCTIONAL TEST - uses real sops binary.
    """
    # Setup secrets directory
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()

    # Create .sops.yaml in secrets directory
    sops_config = secrets_dir / ".sops.yaml"
    sops_config.write_text(
        f"""creation_rules:
  - age: {real_age_key["public_key"]}
"""
    )

    # Create and encrypt a file using real sops
    plaintext_content = "DB_PASSWORD=secret123\nAPI_KEY=xyz789"
    plaintext_tmp = tmp_path / "temp.txt"
    plaintext_tmp.write_text(plaintext_content)

    encrypted = secrets_dir / "test.enc.txt"

    env = {
        **os.environ,
        "SOPS_AGE_KEY_FILE": str(real_age_key["private_key_file"]),
    }

    subprocess.run(
        [
            "sops",
            "-e",
            "--age",
            real_age_key["public_key"],
            "--output",
            str(encrypted),
            str(plaintext_tmp),
        ],
        check=True,
        env=env,
    )

    plaintext_tmp.unlink()

    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    runner = CliRunner(env=env)
    result = runner.invoke(decrypt, ["test"])

    # Command should succeed
    assert result.exit_code == 0, f"Decrypt failed: {result.output}"

    # Verify plaintext file was created
    plaintext = secrets_dir / "test.txt"
    assert plaintext.exists(), "Decrypted file should exist"

    # Verify content matches original
    assert plaintext.read_text() == plaintext_content, "Decrypted content should match original"


def test_decrypt_no_secrets_directory(tmp_path, monkeypatch):
    """Test decrypt command when secrets/ directory doesn't exist."""
    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(decrypt, [])

    assert result.exit_code == 1
    assert SECRETS_DIR_NOT_FOUND in result.output


def test_decrypt_file_not_found(tmp_path, monkeypatch):
    """Test decrypt command when specific file doesn't exist."""
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()

    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(decrypt, ["nonexistent"])

    assert result.exit_code == 1
    assert FILE_NOT_FOUND in result.output


def test_decrypt_no_encrypted_files(tmp_path, monkeypatch):
    """Test decrypt command when no encrypted files exist."""
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()

    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(decrypt, [])

    assert result.exit_code == 0
    assert NO_ENCRYPTED_SECRETS in result.output


def test_decrypt_failure_handling(tmp_path, monkeypatch):
    """Test decrypt command handles decryption failures."""
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()

    # Create corrupted "encrypted" file
    encrypted = secrets_dir / "corrupted.enc.txt"
    encrypted.write_text("This is not a valid SOPS encrypted file")

    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(decrypt, ["corrupted"])

    assert result.exit_code == 1
    assert FAILED_TO_DECRYPT in result.output
