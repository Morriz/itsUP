#!/usr/bin/env python3

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from click.testing import CliRunner
from commands.encrypt import encrypt


class TestEncryptCommand(unittest.TestCase):
    """Tests for encrypt command"""

    def setUp(self):
        """Set up test fixtures"""
        self.runner = CliRunner()

    def test_encrypt_help(self) -> None:
        """Test encrypt help command."""
        result = self.runner.invoke(encrypt, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Encrypt secrets with SOPS", result.output)

    @patch("commands.encrypt.is_sops_available", return_value=False)
    def test_encrypt_fails_without_sops(self, mock_sops: Mock) -> None:
        """Test that encrypt fails gracefully when SOPS not installed."""
        result = self.runner.invoke(encrypt)
        self.assertEqual(result.exit_code, 1)
        self.assertIn("SOPS is not installed", result.output)


if __name__ == "__main__":
    unittest.main()
