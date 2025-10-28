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
import importlib.machinery

test_dir = os.path.dirname(os.path.abspath(__file__))
itsup_path = os.path.join(test_dir, "bin", "itsup")

# Use SourceFileLoader for extensionless Python files
loader = importlib.machinery.SourceFileLoader("itsup", itsup_path)
spec = importlib.util.spec_from_loader(loader.name, loader)
if spec is None or spec.loader is None:
    raise ImportError(f"Could not load itsup module from {itsup_path}")
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

    def test_verbose_flag(self) -> None:
        """Test that --verbose flag is accepted."""
        result = self.runner.invoke(itsup_module.cli, ["--verbose", "--help"])
        self.assertEqual(result.exit_code, 0)

    def test_no_verbose_flag(self) -> None:
        """Test that CLI works without --verbose flag."""
        result = self.runner.invoke(itsup_module.cli, ["--help"])
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

    def test_run_command_registered(self) -> None:
        """Test that run command is registered."""
        result = self.runner.invoke(itsup_module.cli, ["run", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Run itsUP stack", result.output)

    def test_dns_command_registered(self) -> None:
        """Test that dns command is registered."""
        result = self.runner.invoke(itsup_module.cli, ["dns", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("DNS stack management", result.output)

    def test_dns_up_subcommand(self) -> None:
        """Test that dns up uses smart deployment (not a separate subcommand)."""
        # DNS uses passthrough pattern - 'up' is intercepted, not a subcommand
        # Just verify the dns command accepts arguments
        result = self.runner.invoke(itsup_module.cli, ["dns", "--help"])

        self.assertEqual(result.exit_code, 0)
        # Should show examples of 'up' usage in help
        self.assertIn("itsup dns up", result.output)

    def test_proxy_command_registered(self) -> None:
        """Test that proxy command is registered."""
        result = self.runner.invoke(itsup_module.cli, ["proxy", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Proxy stack management", result.output)

    def test_proxy_up_subcommand(self) -> None:
        """Test that proxy up uses smart deployment (not a separate subcommand)."""
        # Proxy uses passthrough pattern - 'up' is intercepted, not a subcommand
        # Just verify the proxy command accepts arguments
        result = self.runner.invoke(itsup_module.cli, ["proxy", "--help"])

        self.assertEqual(result.exit_code, 0)
        # Should show examples of 'up' usage in help
        self.assertIn("itsup proxy up", result.output)

    def test_monitor_command_registered(self) -> None:
        """Test that monitor command is registered."""
        result = self.runner.invoke(itsup_module.cli, ["monitor", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Container security monitor", result.output)

    def test_monitor_start_command_registered(self) -> None:
        """Test that monitor start subcommand is registered."""
        result = self.runner.invoke(itsup_module.cli, ["monitor", "start", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Start container security monitor", result.output)

    def test_down_command_registered(self) -> None:
        """Test that down command is registered."""
        result = self.runner.invoke(itsup_module.cli, ["down", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Stop ALL containers", result.output)

    def test_down_clean_flag(self) -> None:
        """Test that down command accepts --clean flag."""
        result = self.runner.invoke(itsup_module.cli, ["down", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--clean", result.output)


if __name__ == "__main__":
    unittest.main()
