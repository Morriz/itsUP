"""
Pytest fixtures for functional tests.

These create REAL encrypted files, REAL git repos, using REAL tools.
NO MOCKING.
"""

import os
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def real_age_key(tmp_path_factory):
    """Generate REAL age encryption key for tests.

    Returns:
        {
            "private_key_file": Path to key file,
            "public_key": Public key string
        }
    """
    key_dir = tmp_path_factory.mktemp("keys")
    key_file = key_dir / "test-key.txt"

    # Generate REAL age key using REAL age binary
    result = subprocess.run(
        ["age-keygen", "-o", str(key_file)],
        capture_output=True,
        text=True,
        check=True,
    )

    # Extract public key from stderr (format: "Public key: age1...")
    public_key = None
    for line in result.stderr.splitlines():
        if line.startswith("Public key:"):
            public_key = line.split(": ", 1)[1].strip()
            break

    assert public_key, f"Failed to generate age key. Output: {result.stderr}"

    return {"private_key_file": key_file, "public_key": public_key}


@pytest.fixture
def sops_config_dir(tmp_path, real_age_key):
    """Create directory with .sops.yaml config for testing.

    Returns:
        Path to directory with .sops.yaml configured for the test age key
    """
    # Create .sops.yaml config
    sops_config = tmp_path / ".sops.yaml"
    sops_config.write_text(
        f"""creation_rules:
  - age: {real_age_key["public_key"]}
"""
    )

    # Set age key environment variable
    os.environ["SOPS_AGE_KEY_FILE"] = str(real_age_key["private_key_file"])

    return tmp_path


@pytest.fixture
def real_encrypted_file(tmp_path, real_age_key):
    """Create REAL encrypted file using REAL sops.

    Returns:
        {
            "file": Path to encrypted file,
            "plaintext": Original content,
            "age_key": Key info
        }
    """
    # Create plaintext secret
    plaintext_content = "SECRET_KEY=test_value_12345\nAPI_TOKEN=abc123def456"
    plaintext_file = tmp_path / "secret.txt"
    plaintext_file.write_text(plaintext_content)

    # Encrypt with REAL sops
    encrypted_file = tmp_path / "secret.enc.txt"
    subprocess.run(
        [
            "sops",
            "-e",
            "--age",
            real_age_key["public_key"],
            "--output",
            str(encrypted_file),
            str(plaintext_file),
        ],
        check=True,
    )

    # Remove plaintext
    plaintext_file.unlink()

    return {
        "file": encrypted_file,
        "plaintext": plaintext_content,
        "age_key": real_age_key,
    }


@pytest.fixture
def real_secrets_repo(tmp_path, real_encrypted_file):
    """Create REAL git repo with REAL encrypted secrets.

    Returns:
        {
            "dir": Path to secrets repo,
            "committed_file": Path to committed encrypted file,
            "plaintext": Original content,
            "age_key": Key info
        }
    """
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()

    # Initialize REAL git repo
    subprocess.run(["git", "init"], cwd=secrets_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=secrets_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=secrets_dir,
        check=True,
        capture_output=True,
    )

    # Copy encrypted file into repo
    committed_file = secrets_dir / "committed.enc.txt"
    committed_file.write_bytes(real_encrypted_file["file"].read_bytes())

    # REALLY commit it
    subprocess.run(["git", "add", "."], cwd=secrets_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add encrypted secrets"],
        cwd=secrets_dir,
        check=True,
        capture_output=True,
    )

    return {
        "dir": secrets_dir,
        "committed_file": committed_file,
        "plaintext": real_encrypted_file["plaintext"],
        "age_key": real_encrypted_file["age_key"],
    }


@pytest.fixture
def itsup_repo_with_secrets(tmp_path, real_secrets_repo):
    """Create itsUP repo structure with real secrets repo.

    Returns:
        {
            "root": itsUP repo root,
            "secrets": secrets repo info
        }
    """
    itsup_root = tmp_path / "itsup"
    itsup_root.mkdir()

    # Create commands/ dir for __file__ mocking
    (itsup_root / "commands").mkdir()

    # Symlink real secrets repo
    secrets_link = itsup_root / "secrets"
    secrets_link.symlink_to(real_secrets_repo["dir"])

    return {"root": itsup_root, "secrets": real_secrets_repo}
