#!/usr/bin/env python3

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from click.testing import CliRunner
from commands.decrypt import decrypt


class TestDecryptCommand(unittest.TestCase):
    """Tests for decrypt command"""

    def setUp(self):
        """Set up test fixtures"""
        self.runner = CliRunner()

    @patch("commands.decrypt.is_sops_available", return_value=False)
    def test_decrypt_fails_without_sops(self, mock_sops: Mock) -> None:
        """Test that decrypt fails gracefully when SOPS not installed."""
        result = self.runner.invoke(decrypt)
        self.assertEqual(result.exit_code, 1)
        self.assertIn("SOPS is not installed", result.output)


if __name__ == "__main__":
    unittest.main()
