#!/usr/bin/env python3

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.sops import (
    decrypt_file,
    decrypt_to_memory,
    encrypt_file,
    is_sops_available,
    load_encrypted_env,
    load_env_file,
)


class TestSOPS(unittest.TestCase):
    """Tests for SOPS encryption/decryption helpers"""

    def test_is_sops_available_when_installed(self) -> None:
        """Test SOPS availability detection when installed."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            self.assertTrue(is_sops_available())
            mock_run.assert_called_once()

    def test_is_sops_available_when_not_installed(self) -> None:
        """Test SOPS availability detection when not installed."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            self.assertFalse(is_sops_available())

    def test_encrypt_file_success(self) -> None:
        """Test successful file encryption."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plaintext_path = Path(tmpdir) / "secret.txt"
            encrypted_path = Path(tmpdir) / "secret.enc.txt"

            # Create plaintext file
            plaintext_path.write_text("SECRET_KEY=mysecret\n")

            with patch("lib.sops.is_sops_available", return_value=True):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = Mock(returncode=0)

                    result = encrypt_file(plaintext_path, encrypted_path)

                    self.assertTrue(result)
                    mock_run.assert_called_once()

    def test_encrypt_file_sops_not_available(self) -> None:
        """Test encryption fails gracefully when SOPS not available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plaintext_path = Path(tmpdir) / "secret.txt"
            encrypted_path = Path(tmpdir) / "secret.enc.txt"

            plaintext_path.write_text("SECRET_KEY=mysecret\n")

            with patch("lib.sops.is_sops_available", return_value=False):
                result = encrypt_file(plaintext_path, encrypted_path)
                self.assertFalse(result)

    def test_encrypt_file_missing_plaintext(self) -> None:
        """Test encryption fails when plaintext file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plaintext_path = Path(tmpdir) / "nonexistent.txt"
            encrypted_path = Path(tmpdir) / "secret.enc.txt"

            with patch("lib.sops.is_sops_available", return_value=True):
                result = encrypt_file(plaintext_path, encrypted_path)
                self.assertFalse(result)

    def test_decrypt_file_success(self) -> None:
        """Test successful file decryption."""
        with tempfile.TemporaryDirectory() as tmpdir:
            encrypted_path = Path(tmpdir) / "secret.enc.txt"
            plaintext_path = Path(tmpdir) / "secret.txt"

            # Create encrypted file (mock)
            encrypted_path.write_text("encrypted content")

            with patch("lib.sops.is_sops_available", return_value=True):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = Mock(returncode=0)

                    result = decrypt_file(encrypted_path, plaintext_path)

                    self.assertTrue(result)
                    mock_run.assert_called_once()

    def test_decrypt_to_memory_success(self) -> None:
        """Test successful decryption to memory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            encrypted_path = Path(tmpdir) / "secret.enc.txt"
            encrypted_path.write_text("encrypted content")

            with patch("lib.sops.is_sops_available", return_value=True):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = Mock(returncode=0, stdout="SECRET_KEY=mysecret\nAPI_KEY=test123\n")

                    result = decrypt_to_memory(encrypted_path)

                    self.assertIsNotNone(result)
                    self.assertIn("SECRET_KEY=mysecret", result)

    def test_decrypt_to_memory_sops_not_available(self) -> None:
        """Test decryption to memory returns None when SOPS unavailable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            encrypted_path = Path(tmpdir) / "secret.enc.txt"
            encrypted_path.write_text("encrypted content")

            with patch("lib.sops.is_sops_available", return_value=False):
                result = decrypt_to_memory(encrypted_path)
                self.assertIsNone(result)

    def test_load_env_file(self) -> None:
        """Test loading environment variables from plaintext file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / "test.txt"
            env_file.write_text("# Comment\n" "SECRET_KEY=mysecret\n" "API_KEY=test123\n" "\n" "DB_PASSWORD=secure\n")

            env_vars = load_env_file(env_file)

            self.assertEqual(len(env_vars), 3)
            self.assertEqual(env_vars["SECRET_KEY"], "mysecret")
            self.assertEqual(env_vars["API_KEY"], "test123")
            self.assertEqual(env_vars["DB_PASSWORD"], "secure")

    def test_load_env_file_missing(self) -> None:
        """Test loading from missing file returns empty dict."""
        env_vars = load_env_file(Path("/nonexistent/file.txt"))
        self.assertEqual(env_vars, {})

    def test_load_encrypted_env_success(self) -> None:
        """Test loading environment variables from encrypted file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            encrypted_path = Path(tmpdir) / "secret.enc.txt"
            encrypted_path.write_text("encrypted")

            with patch("lib.sops.decrypt_to_memory") as mock_decrypt:
                mock_decrypt.return_value = "SECRET_KEY=encrypted_value\n" "API_KEY=test123\n"

                env_vars = load_encrypted_env(encrypted_path)

                self.assertEqual(len(env_vars), 2)
                self.assertEqual(env_vars["SECRET_KEY"], "encrypted_value")
                self.assertEqual(env_vars["API_KEY"], "test123")

    def test_load_encrypted_env_decrypt_fails(self) -> None:
        """Test loading encrypted env returns empty dict on decrypt failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            encrypted_path = Path(tmpdir) / "secret.enc.txt"
            encrypted_path.write_text("encrypted")

            with patch("lib.sops.decrypt_to_memory", return_value=None):
                env_vars = load_encrypted_env(encrypted_path)
                self.assertEqual(env_vars, {})


if __name__ == "__main__":
    unittest.main()
