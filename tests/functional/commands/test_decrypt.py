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
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from click.testing import CliRunner

from commands.decrypt import decrypt


def test_decrypt_command_with_real_sops(tmp_path, real_age_key):
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

    # Create commands directory for __file__ mocking
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()

    # Mock __file__ to point to our tmp directory
    with patch("commands.decrypt.__file__", str(commands_dir / "decrypt.py")):
        runner = CliRunner(env=env)
        result = runner.invoke(decrypt, ["test"])

    # Command should succeed
    assert result.exit_code == 0, f"Decrypt failed: {result.output}"

    # Verify plaintext file was created
    plaintext = secrets_dir / "test.txt"
    assert plaintext.exists(), "Decrypted file should exist"

    # Verify content matches original
    assert plaintext.read_text() == plaintext_content, "Decrypted content should match original"


def test_decrypt_no_secrets_directory(tmp_path):
    """Test decrypt command when secrets/ directory doesn't exist."""
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()

    with patch("commands.decrypt.__file__", str(commands_dir / "decrypt.py")):
        runner = CliRunner()
        result = runner.invoke(decrypt, [])

    assert result.exit_code == 1
    assert "secrets/ directory not found" in result.output


def test_decrypt_file_not_found(tmp_path):
    """Test decrypt command when specific file doesn't exist."""
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()

    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()

    with patch("commands.decrypt.__file__", str(commands_dir / "decrypt.py")):
        runner = CliRunner()
        result = runner.invoke(decrypt, ["nonexistent"])

    assert result.exit_code == 1
    assert "File not found: secrets/nonexistent.enc.txt" in result.output


def test_decrypt_no_encrypted_files(tmp_path):
    """Test decrypt command when no encrypted files exist."""
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()

    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()

    with patch("commands.decrypt.__file__", str(commands_dir / "decrypt.py")):
        runner = CliRunner()
        result = runner.invoke(decrypt, [])

    assert result.exit_code == 0
    assert "No encrypted secrets found" in result.output


def test_decrypt_failure_handling(tmp_path):
    """Test decrypt command handles decryption failures."""
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()

    # Create corrupted "encrypted" file
    encrypted = secrets_dir / "corrupted.enc.txt"
    encrypted.write_text("This is not a valid SOPS encrypted file")

    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()

    with patch("commands.decrypt.__file__", str(commands_dir / "decrypt.py")):
        runner = CliRunner()
        result = runner.invoke(decrypt, ["corrupted"])

    assert result.exit_code == 1
    assert "Failed to decrypt" in result.output
