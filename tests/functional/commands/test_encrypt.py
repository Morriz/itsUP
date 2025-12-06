#!/usr/bin/env python3

"""
Functional tests for 'itsup encrypt' command.

Uses REAL sops binary for encryption.
NO MOCKING.
"""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from click.testing import CliRunner

from commands.encrypt import encrypt
from lib.sops import encrypt_file


def test_encrypt_command_with_real_sops(tmp_path, real_age_key):
    """Test 'itsup encrypt' command end-to-end.

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

    # Create plaintext secret
    plaintext = secrets_dir / "test.txt"
    plaintext_content = "SECRET_KEY=test_value\nAPI_TOKEN=abc123"
    plaintext.write_text(plaintext_content)

    # Setup environment
    env = {
        **os.environ,
        "SOPS_AGE_KEY_FILE": str(real_age_key["private_key_file"]),
    }

    # Create commands directory for __file__ mocking
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()

    # Mock __file__ to point to our tmp directory
    with patch("commands.encrypt.__file__", str(commands_dir / "encrypt.py")):
        runner = CliRunner(env=env)
        result = runner.invoke(encrypt, ["test"])

    # Command should succeed
    assert result.exit_code == 0, f"Encrypt failed: {result.output}"

    # Verify encrypted file was created
    encrypted = secrets_dir / "test.enc.txt"
    assert encrypted.exists(), "Encrypted file should exist"

    # Verify content is actually encrypted (not plaintext)
    encrypted_content = encrypted.read_text()
    assert plaintext_content not in encrypted_content, "Content should be encrypted"
    assert "sops" in encrypted_content, "Should contain SOPS metadata"

    # Verify we can decrypt with real sops
    decrypted_content = subprocess.run(
        ["sops", "-d", str(encrypted)],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    ).stdout

    assert decrypted_content == plaintext_content, "Decrypted content should match original"


def test_encrypt_temp_plaintext_uses_secrets_config(tmp_path, real_age_key):
    """Ensure encryption uses secrets/.sops.yaml when plaintext lives elsewhere."""
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()

    sops_config = secrets_dir / ".sops.yaml"
    sops_config.write_text(
        f"""creation_rules:
  - age: {real_age_key["public_key"]}
"""
    )

    plaintext = tmp_path / "temp-edit.txt"
    plaintext_content = "API_TOKEN=temp123"
    plaintext.write_text(plaintext_content)

    encrypted = secrets_dir / "temp-edit.enc.txt"

    env = {
        **os.environ,
        "SOPS_AGE_KEY_FILE": str(real_age_key["private_key_file"]),
    }

    with patch.dict(os.environ, env, clear=False):
        success, was_encrypted = encrypt_file(plaintext, encrypted, force=True)

    assert success is True, "Encryption should succeed using secrets/.sops.yaml"
    assert was_encrypted is True, "Plaintext was new so it should be encrypted"
    assert encrypted.exists(), "Encrypted file should be created in secrets/"

    decrypted_content = subprocess.run(
        ["sops", "-d", str(encrypted)],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    ).stdout

    assert decrypted_content == plaintext_content, "Decrypted content should match original"


def test_encrypt_with_delete_flag(tmp_path, real_age_key):
    """Test 'itsup encrypt --delete' removes plaintext files.

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

    # Create plaintext secret
    plaintext = secrets_dir / "delete-test.txt"
    plaintext.write_text("SECRET=value")

    env = {
        **os.environ,
        "SOPS_AGE_KEY_FILE": str(real_age_key["private_key_file"]),
    }

    # Create commands directory for __file__ mocking
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()

    # Encrypt with --delete flag
    with patch("commands.encrypt.__file__", str(commands_dir / "encrypt.py")):
        runner = CliRunner(env=env)
        result = runner.invoke(encrypt, ["delete-test", "--delete"])

    assert result.exit_code == 0, f"Encrypt failed: {result.output}"

    # Verify encrypted file exists
    encrypted = secrets_dir / "delete-test.enc.txt"
    assert encrypted.exists(), "Encrypted file should exist"

    # Verify plaintext was deleted
    assert not plaintext.exists(), "Plaintext should be deleted with --delete flag"


def test_encrypt_skip_unchanged(tmp_path, real_age_key):
    """Test 'itsup encrypt' skips files when content is unchanged.

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

    # Create plaintext secret
    plaintext = secrets_dir / "unchanged.txt"
    plaintext_content = "UNCHANGED_KEY=value"
    plaintext.write_text(plaintext_content)

    env = {
        **os.environ,
        "SOPS_AGE_KEY_FILE": str(real_age_key["private_key_file"]),
    }

    # Create commands directory for __file__ mocking
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()

    runner = CliRunner(env=env)

    # First encryption
    with patch("commands.encrypt.__file__", str(commands_dir / "encrypt.py")):
        result = runner.invoke(encrypt, ["unchanged"])
    assert result.exit_code == 0
    assert "Encrypted 1 file" in result.output, "Should encrypt on first run"

    # Second encryption (content unchanged)
    with patch("commands.encrypt.__file__", str(commands_dir / "encrypt.py")):
        result = runner.invoke(encrypt, ["unchanged"])
    assert result.exit_code == 0
    assert "Skipped 1 file" in result.output, "Should skip unchanged file"

    # Force re-encryption
    with patch("commands.encrypt.__file__", str(commands_dir / "encrypt.py")):
        result = runner.invoke(encrypt, ["unchanged", "--force"])
    assert result.exit_code == 0
    assert "Encrypted 1 file" in result.output, "Should re-encrypt with --force"


def test_encrypt_no_secrets_directory(tmp_path):
    """Test encrypt command when secrets/ directory doesn't exist."""
    # Create commands directory for __file__ mocking (but no secrets/)
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()

    with patch("commands.encrypt.__file__", str(commands_dir / "encrypt.py")):
        runner = CliRunner()
        result = runner.invoke(encrypt, [])

    assert result.exit_code == 1
    assert "secrets/ directory not found" in result.output


def test_encrypt_file_not_found(tmp_path):
    """Test encrypt command when specific file doesn't exist."""
    # Create empty secrets directory
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()

    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()

    with patch("commands.encrypt.__file__", str(commands_dir / "encrypt.py")):
        runner = CliRunner()
        result = runner.invoke(encrypt, ["nonexistent"])

    assert result.exit_code == 1
    assert "File not found: secrets/nonexistent.txt" in result.output


def test_encrypt_no_plaintext_files(tmp_path):
    """Test encrypt command when no plaintext files exist."""
    # Create empty secrets directory
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()

    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()

    with patch("commands.encrypt.__file__", str(commands_dir / "encrypt.py")):
        runner = CliRunner()
        result = runner.invoke(encrypt, [])

    assert result.exit_code == 0
    assert "No plaintext secrets found" in result.output


def test_encrypt_failure_handling(tmp_path, real_age_key):
    """Test encrypt command handles encryption failures."""
    # Setup secrets directory WITHOUT .sops.yaml
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()

    # Create plaintext (but encryption will fail without .sops.yaml)
    plaintext = secrets_dir / "test.txt"
    plaintext.write_text("SECRET=value")

    env = {
        **os.environ,
        "SOPS_AGE_KEY_FILE": str(real_age_key["private_key_file"]),
    }

    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()

    with patch("commands.encrypt.__file__", str(commands_dir / "encrypt.py")):
        runner = CliRunner(env=env)
        result = runner.invoke(encrypt, ["test"])

    assert result.exit_code == 1
    assert "Failed to encrypt" in result.output
