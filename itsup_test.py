#!/usr/bin/env python3

import os
import sys
import unittest
from unittest import mock
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from click.testing import CliRunner

# Import the CLI group
import importlib.util

spec = importlib.util.spec_from_file_location("itsup", "itsup")
itsup_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(itsup_module)


class TestCLI(unittest.TestCase):
    """Tests for main CLI integration"""

    def setUp(self):
        """Set up test fixtures"""
        self.runner = CliRunner()

    def test_cli_help(self) -> None:
        """Test that CLI help works."""
        result = self.runner.invoke(itsup_module.cli, ["--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("itsUP - Infrastructure management CLI", result.output)

    def test_cli_version(self) -> None:
        """Test that CLI version works."""
        result = self.runner.invoke(itsup_module.cli, ["--version"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("0.1.0", result.output)

    @patch("lib.logging_config.setup_logging")
    def test_verbose_flag(self, mock_setup_logging: Mock) -> None:
        """Test that --verbose flag sets DEBUG logging level."""
        result = self.runner.invoke(itsup_module.cli, ["--verbose", "--help"])

        # Verify setup_logging was called with DEBUG level
        mock_setup_logging.assert_called_once_with(level="DEBUG")
        self.assertEqual(result.exit_code, 0)

    @patch("lib.logging_config.setup_logging")
    def test_no_verbose_flag(self, mock_setup_logging: Mock) -> None:
        """Test that without --verbose flag, INFO logging level is used."""
        result = self.runner.invoke(itsup_module.cli, ["--help"])

        # Verify setup_logging was called with INFO level
        mock_setup_logging.assert_called_once_with(level="INFO")
        self.assertEqual(result.exit_code, 0)

    def test_init_command_registered(self) -> None:
        """Test that init command is registered."""
        result = self.runner.invoke(itsup_module.cli, ["init", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Initialize", result.output)

    def test_apply_command_registered(self) -> None:
        """Test that apply command is registered."""
        result = self.runner.invoke(itsup_module.cli, ["apply", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Apply configurations", result.output)

    def test_svc_command_registered(self) -> None:
        """Test that svc command is registered."""
        result = self.runner.invoke(itsup_module.cli, ["svc", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Service operations", result.output)

    def test_validate_command_registered(self) -> None:
        """Test that validate command is registered."""
        result = self.runner.invoke(itsup_module.cli, ["validate", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Validate", result.output)


if __name__ == "__main__":
    unittest.main()
