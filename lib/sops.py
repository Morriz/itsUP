#!/usr/bin/env python3

"""
SOPS encryption/decryption helpers for secret management.

Provides transparent encryption of secrets/*.txt files using SOPS.
"""

import logging
import subprocess
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def is_sops_available() -> bool:
    """Check if SOPS is installed and available."""
    try:
        subprocess.run(["sops", "--version"], capture_output=True, check=True, timeout=5)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def encrypt_file(plaintext_path: Path, encrypted_path: Path) -> bool:
    """
    Encrypt a plaintext file using SOPS.

    Args:
        plaintext_path: Path to plaintext file
        encrypted_path: Path where encrypted file should be saved

    Returns:
        True if successful, False otherwise
    """
    try:
        if not is_sops_available():
            logger.error("SOPS is not installed. Install with: brew install sops")
            return False

        if not plaintext_path.exists():
            logger.error("Plaintext file not found: %s", plaintext_path)
            return False

        # Encrypt: sops -e plaintext.txt > encrypted.enc.txt
        with open(encrypted_path, "w", encoding="utf-8") as outfile:
            subprocess.run(["sops", "-e", str(plaintext_path)], stdout=outfile, check=True, text=True)

        logger.info("✓ Encrypted %s → %s", plaintext_path.name, encrypted_path.name)
        return True

    except subprocess.CalledProcessError as e:
        logger.error("✗ Failed to encrypt %s: %s", plaintext_path.name, e)
        return False


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
        with open(plaintext_path, "w", encoding="utf-8") as outfile:
            subprocess.run(["sops", "-d", str(encrypted_path)], stdout=outfile, check=True, text=True)

        logger.info("✓ Decrypted %s → %s", encrypted_path.name, plaintext_path.name)
        return True

    except subprocess.CalledProcessError as e:
        logger.error("✗ Failed to decrypt %s: %s", encrypted_path.name, e)
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
        if not is_sops_available():
            logger.warning("SOPS not available, cannot decrypt %s", encrypted_path.name)
            return None

        if not encrypted_path.exists():
            return None

        # Decrypt to stdout
        result = subprocess.run(["sops", "-d", str(encrypted_path)], capture_output=True, check=True, text=True)

        return result.stdout

    except subprocess.CalledProcessError as e:
        logger.error("✗ Failed to decrypt %s: %s", encrypted_path.name, e)
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
