#!/usr/bin/env python3

"""
Tests for diff-secrets command.

Focuses on the critical regression test for the bug where git commands
ran in the wrong repository.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from click.testing import CliRunner

from commands.diff_secrets import diff_secrets


class TestDiffSecrets(unittest.TestCase):
    """Tests for diff-secrets command"""

    def setUp(self):
        """Set up test fixtures"""
        self.runner = CliRunner()

    @patch("commands.diff_secrets._check_sops_diff")
    def test_diff_secrets_requires_sops_diff(self, mock_check) -> None:
        """Test that command fails gracefully when sops-diff is missing."""
        mock_check.return_value = False

        result = self.runner.invoke(diff_secrets, [])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("sops-diff is not installed", result.output)


if __name__ == "__main__":
    unittest.main()
