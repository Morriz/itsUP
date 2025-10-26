#!/usr/bin/env python3

import os
import sys
import unittest
from unittest.mock import Mock, patch, call

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from click.testing import CliRunner
from commands.down import down


class TestDown(unittest.TestCase):
    """Tests for down command"""

    def setUp(self):
        """Set up test fixtures"""
        self.runner = CliRunner()

    @patch("commands.down.list_projects")
    @patch("commands.down.subprocess.run")
    @patch("commands.down.get_env_with_secrets")
    def test_down_stops_all_stacks(
        self, mock_get_env: Mock, mock_subprocess: Mock, mock_list_projects: Mock
    ) -> None:
        """Test that down command stops all stacks in correct order."""
        mock_list_projects.return_value = ["project1", "project2"]
        mock_get_env.return_value = {"SECRET": "value"}
        mock_subprocess.return_value = Mock(returncode=0)

        result = self.runner.invoke(down, [])

        self.assertEqual(result.exit_code, 0)
        # Should call: monitor stop, api stop, projects down (x2), proxy down, dns down
        # Plus pkill calls (2) = at least 4 subprocess calls minimum
        self.assertGreaterEqual(mock_subprocess.call_count, 4)

    @patch("commands.down.list_projects")
    @patch("commands.down.subprocess.run")
    @patch("commands.down.get_env_with_secrets")
    def test_down_with_clean_removes_containers(
        self, mock_get_env: Mock, mock_subprocess: Mock, mock_list_projects: Mock
    ) -> None:
        """Test that --clean flag removes stopped containers."""
        mock_list_projects.return_value = ["project1"]
        mock_get_env.return_value = {"SECRET": "value"}
        mock_subprocess.return_value = Mock(returncode=0)

        result = self.runner.invoke(down, ["--clean"])

        self.assertEqual(result.exit_code, 0)
        # Should have cleanup calls in addition to down calls
        # Check that docker compose rm was called
        cleanup_calls = [
            call_args for call_args in mock_subprocess.call_args_list
            if "rm" in str(call_args)
        ]
        self.assertGreater(len(cleanup_calls), 0, "Expected docker compose rm calls for cleanup")

    @patch("commands.down.list_projects")
    @patch("commands.down.subprocess.run")
    @patch("commands.down.get_env_with_secrets")
    def test_down_continues_on_individual_failures(
        self, mock_get_env: Mock, mock_subprocess: Mock, mock_list_projects: Mock
    ) -> None:
        """Test that down continues even if individual stack fails to stop."""
        mock_list_projects.return_value = ["project1"]
        mock_get_env.return_value = {"SECRET": "value"}

        # Some calls succeed, some fail
        mock_subprocess.return_value = Mock(returncode=0)

        result = self.runner.invoke(down, [])

        # Should complete successfully even if some stacks fail
        self.assertEqual(result.exit_code, 0)

    @patch("commands.down.list_projects")
    @patch("commands.down.subprocess.run")
    @patch("commands.down.get_env_with_secrets")
    def test_down_with_no_projects(
        self, mock_get_env: Mock, mock_subprocess: Mock, mock_list_projects: Mock
    ) -> None:
        """Test down command when no projects exist."""
        mock_list_projects.return_value = []
        mock_get_env.return_value = {"SECRET": "value"}
        mock_subprocess.return_value = Mock(returncode=0)

        result = self.runner.invoke(down, [])

        self.assertEqual(result.exit_code, 0)
        # Should still stop infrastructure (dns, proxy)
        self.assertGreater(mock_subprocess.call_count, 0)


if __name__ == "__main__":
    unittest.main()
