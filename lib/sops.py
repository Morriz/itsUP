#!/usr/bin/env python3

"""
SOPS encryption/decryption helpers for secret management.

Provides transparent encryption of secrets/*.txt files using SOPS.
"""

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from instrukt_ai_logging import get_logger

logger = get_logger(f"itsup.{__name__}")


@dataclass(frozen=True)
class SecretsEncryptResult:
    """Outcome of an `encrypt_plaintext_secrets` run, partitioned by file."""

    encrypted: tuple[Path, ...] = ()
    skipped: tuple[Path, ...] = ()
    failed: tuple[Path, ...] = ()


def is_sops_available() -> bool:
    """Check if SOPS is installed and available."""
    try:
        subprocess.run(["sops", "--version"], capture_output=True, check=True, timeout=5)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of file content."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def encrypt_file(plaintext_path: Path, encrypted_path: Path, force: bool = False) -> tuple[bool, bool]:
    """
    Encrypt a plaintext file using SOPS.

    Skips encryption if the encrypted file already exists and contains the same
    content (based on SHA256 hash comparison). This prevents unnecessary
    re-encryption which would create new git hashes even for unchanged content.

    Args:
        plaintext_path: Path to plaintext file
        encrypted_path: Path where encrypted file should be saved
        force: If True, always re-encrypt even if content is unchanged

    Returns:
        Tuple of (success: bool, encrypted: bool)
        - success: True if operation succeeded (encrypted or skipped)
        - encrypted: True if file was actually encrypted, False if skipped
    """
    try:
        if not is_sops_available():
            logger.error("SOPS is not installed. Install with: brew install sops")
            return (False, False)

        if not plaintext_path.exists():
            logger.error("Plaintext file not found: %s", plaintext_path)
            return (False, False)

        # Skip if encrypted file exists and content is identical (unless force=True)
        if not force and encrypted_path.exists():
            # Decrypt existing file to memory and compare hashes
            decrypted_content = decrypt_to_memory(encrypted_path)
            if decrypted_content is not None:
                # Compute hash of plaintext file
                plaintext_hash = _compute_file_hash(plaintext_path)

                # Compute hash of decrypted content
                decrypted_hash = hashlib.sha256(decrypted_content.encode()).hexdigest()

                if plaintext_hash == decrypted_hash:
                    logger.info("⊙ Skipped %s (unchanged)", plaintext_path.name)
                    return (True, False)  # Success but not encrypted (skipped)

        # Encrypt: sops -e plaintext.txt > encrypted.enc.txt
        # Use --config from the encrypted file's directory (secrets/)
        config_file = encrypted_path.parent / ".sops.yaml"
        if not config_file.exists():
            logger.error("SOPS config not found: %s", config_file)
            return (False, False)
        cmd = ["sops", "--config", str(config_file), "-e", str(plaintext_path)]
        logger.debug("Encrypting: %s → %s", plaintext_path, encrypted_path)
        logger.debug("Command: %s", " ".join(cmd))

        # Encrypt to a temp sibling first: opening encrypted_path directly
        # would truncate the existing encrypted file before SOPS confirms
        # success, corrupting it on a nonzero SOPS run. Replace only after
        # the subprocess succeeds; always clean up the temp file.
        tmp_path = encrypted_path.with_name(f".{encrypted_path.name}.tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as outfile:
                subprocess.run(cmd, stdout=outfile, check=True, text=True)
            tmp_path.replace(encrypted_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        logger.debug("Encrypted %s → %s", plaintext_path.name, encrypted_path.name)
        return (True, True)  # Success and encrypted

    except subprocess.CalledProcessError as e:
        logger.error("Failed to encrypt %s: %s", plaintext_path.name, e)
        return (False, False)


def encrypt_plaintext_secrets(
    secrets_dir: Path, *, name: Optional[str] = None, delete: bool = False, force: bool = False
) -> SecretsEncryptResult:
    """
    Encrypt plaintext secrets under `secrets_dir` in-process (no shell-out).

    Selection is explicit: with `name` given, selects exactly
    `secrets_dir/<name>.txt`; with `name=None`, selects every plaintext
    `*.txt` (excluding `*.enc.txt`). Each selected file is encrypted via
    `encrypt_file` (whose unchanged-content skip populates `skipped`);
    plaintext is deleted only for that file's own success when
    `delete=True`. Never raises for a per-file failure — callers inspect
    `result.failed` and decide how to react.

    Args:
        secrets_dir: Directory containing plaintext/encrypted secret pairs.
        name: When given, encrypt only `<name>.txt`; otherwise all plaintext.
        delete: If True, delete each file's plaintext after its own success.
        force: If True, always re-encrypt even if content is unchanged.

    Returns:
        SecretsEncryptResult partitioning the selected files by outcome.
    """
    if name is not None:
        plaintext_files = [secrets_dir / f"{name}.txt"]
    else:
        plaintext_files = [f for f in secrets_dir.glob("*.txt") if not f.name.endswith(".enc.txt")]

    encrypted: list[Path] = []
    skipped: list[Path] = []
    failed: list[Path] = []

    for plaintext_path in plaintext_files:
        encrypted_path = plaintext_path.with_suffix(".enc.txt")
        success, was_encrypted = encrypt_file(plaintext_path, encrypted_path, force=force)

        if not success:
            failed.append(plaintext_path)
            continue

        if was_encrypted:
            encrypted.append(plaintext_path)
        else:
            skipped.append(plaintext_path)

        if delete:
            plaintext_path.unlink()

    return SecretsEncryptResult(encrypted=tuple(encrypted), skipped=tuple(skipped), failed=tuple(failed))


def decrypt_file(encrypted_path: Path, plaintext_path: Path) -> bool:
    """
    Decrypt a SOPS-encrypted file.

    Args:
        encrypted_path: Path to encrypted file
        plaintext_path: Path where plaintext should be saved

    Returns:
        True if successful, False otherwise
    """
    try:
        if not is_sops_available():
            logger.error("SOPS is not installed. Install with: brew install sops")
            return False

        if not encrypted_path.exists():
            logger.error("Encrypted file not found: %s", encrypted_path)
            return False

        # Decrypt: sops -d encrypted.enc.txt > plaintext.txt
        # Use --config to point to .sops.yaml in the secrets directory
        config_file = encrypted_path.parent / ".sops.yaml"
        cmd = ["sops", "--config", str(config_file), "-d", str(encrypted_path)]
        logger.debug("Decrypting: %s → %s", encrypted_path, plaintext_path)
        logger.debug("Command: %s", " ".join(cmd))
        with open(plaintext_path, "w", encoding="utf-8") as outfile:
            subprocess.run(cmd, stdout=outfile, check=True, text=True)

        logger.debug("Decrypted %s → %s", encrypted_path.name, plaintext_path.name)
        return True

    except subprocess.CalledProcessError as e:
        logger.error("Failed to decrypt %s: %s", encrypted_path.name, e)
        return False


def decrypt_to_memory(encrypted_path: Path) -> Optional[str]:
    """
    Decrypt a SOPS-encrypted file directly to memory (never writes plaintext to disk).

    Args:
        encrypted_path: Path to encrypted file

    Returns:
        Decrypted content as string, or None if failed
    """
    try:
        # Ensure we have a Path object (but don't break mocks in tests)
        if not isinstance(encrypted_path, Path):
            try:
                encrypted_path = Path(encrypted_path)
            except (TypeError, AttributeError):
                # Mock object in tests - pass through
                pass

        if not is_sops_available():
            logger.warning("SOPS not available, cannot decrypt %s", encrypted_path.name)
            return None

        if not encrypted_path.exists():
            return None

        # Decrypt to stdout
        # Use --config to point to .sops.yaml in the secrets directory
        config_file = encrypted_path.parent / ".sops.yaml"
        cmd = ["sops", "--config", str(config_file), "-d", str(encrypted_path)]
        logger.debug("Decrypting to memory: %s", encrypted_path)
        logger.debug("Command: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, check=True, text=True)

        return result.stdout

    except subprocess.CalledProcessError as e:
        logger.error("Failed to decrypt %s: %s", encrypted_path.name, e)
        return None


def load_env_file(file_path: Path) -> Dict[str, str]:
    """
    Load environment variables from a file (KEY=value format).

    Args:
        file_path: Path to env file

    Returns:
        Dictionary of environment variables
    """
    env_vars: Dict[str, str] = {}

    if not file_path.exists():
        return env_vars

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue

            # Parse KEY=value
            if "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()

    return env_vars


def load_encrypted_env(encrypted_path: Path) -> Dict[str, str]:
    """
    Load environment variables from an encrypted file.

    Decrypts to memory only (never writes plaintext to disk).

    Args:
        encrypted_path: Path to encrypted env file

    Returns:
        Dictionary of environment variables
    """
    content = decrypt_to_memory(encrypted_path)
    if not content:
        return {}

    env_vars = {}
    for line in content.splitlines():
        line = line.strip()
        # Skip comments and empty lines
        if not line or line.startswith("#"):
            continue

        # Parse KEY=value
        if "=" in line:
            key, value = line.split("=", 1)
            env_vars[key.strip()] = value.strip()

    return env_vars
