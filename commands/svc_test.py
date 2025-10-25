#!/usr/bin/env python3

import os
import sys
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import Mock, MagicMock, mock_open, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from click.testing import CliRunner

from commands.svc import complete_project, complete_svc_command, svc


class TestSvc(unittest.TestCase):
    """Tests for svc command"""

    def setUp(self):
        """Set up test fixtures"""
        self.runner = CliRunner()

    @patch("commands.svc.list_projects")
    @patch("commands.svc.subprocess.run")
    def test_svc_valid_project(self, mock_subprocess: Mock, mock_list_projects: Mock) -> None:
        """Test running svc command with valid project."""
        mock_list_projects.return_value = ["myproject", "other"]
        mock_subprocess.return_value = Mock(returncode=0)

        result = self.runner.invoke(svc, ["myproject", "ps"])

        self.assertEqual(result.exit_code, 0)
        mock_subprocess.assert_called_once()

    @patch("commands.svc.list_projects")
    def test_svc_invalid_project(self, mock_list_projects: Mock) -> None:
        """Test running svc command with invalid project."""
        mock_list_projects.return_value = ["other", "another"]

        result = self.runner.invoke(svc, ["nonexistent", "ps"])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Project 'nonexistent' not found", result.output)
        self.assertIn("Available: other, another", result.output)

    @patch("commands.svc.list_projects")
    @patch("commands.svc.subprocess.run")
    def test_svc_with_service_name(self, mock_subprocess: Mock, mock_list_projects: Mock) -> None:
        """Test running svc command with service name."""
        mock_list_projects.return_value = ["myproject"]
        mock_subprocess.return_value = Mock(returncode=0)

        result = self.runner.invoke(svc, ["myproject", "logs", "web"])

        self.assertEqual(result.exit_code, 0)
        # Verify that 'web' is passed to docker compose
        call_args = mock_subprocess.call_args[0][0]
        self.assertIn("web", call_args)

    @patch("commands.svc.list_projects")
    @patch("commands.svc.subprocess.run")
    def test_svc_with_flags(self, mock_subprocess: Mock, mock_list_projects: Mock) -> None:
        """Test running svc command with flags."""
        mock_list_projects.return_value = ["myproject"]
        mock_subprocess.return_value = Mock(returncode=0)

        result = self.runner.invoke(svc, ["myproject", "logs", "-f", "web"])

        self.assertEqual(result.exit_code, 0)
        # Verify that flags are passed through
        call_args = mock_subprocess.call_args[0][0]
        self.assertIn("-f", call_args)
        self.assertIn("web", call_args)

    @patch("commands.svc.list_projects")
    @patch("commands.svc.subprocess.run")
    def test_svc_command_failure(self, mock_subprocess: Mock, mock_list_projects: Mock) -> None:
        """Test handling docker compose command failure."""
        mock_list_projects.return_value = ["myproject"]
        mock_subprocess.side_effect = lambda *args, **kwargs: (_ for _ in ()).throw(
            __import__("subprocess").CalledProcessError(1, "docker")
        )

        result = self.runner.invoke(svc, ["myproject", "ps"])

        self.assertEqual(result.exit_code, 1)


class TestAutocompletion(unittest.TestCase):
    """Tests for autocompletion functions"""

    @patch("commands.svc.list_projects")
    def test_complete_project(self, mock_list_projects: Mock) -> None:
        """Test project name autocompletion."""
        mock_list_projects.return_value = ["project1", "project2", "other"]

        result = complete_project(None, None, "proj")

        self.assertEqual(result, ["project1", "project2"])

    @patch("commands.svc.list_projects")
    def test_complete_project_no_match(self, mock_list_projects: Mock) -> None:
        """Test project name autocompletion with no matches."""
        mock_list_projects.return_value = ["project1", "project2"]

        result = complete_project(None, None, "xyz")

        self.assertEqual(result, [])

    def test_complete_svc_command_docker_commands(self) -> None:
        """Test docker compose command autocompletion."""
        ctx = Mock()
        ctx.params = {"command": [], "project": "myproject"}

        result = complete_svc_command(ctx, None, "lo")

        self.assertIn("logs", result)
        self.assertEqual(len(result), 1)

    def test_complete_svc_command_all_commands(self) -> None:
        """Test getting all docker compose commands."""
        ctx = Mock()
        ctx.params = {"command": [], "project": "myproject"}

        result = complete_svc_command(ctx, None, "")

        # Should return common docker compose commands
        self.assertIn("up", result)
        self.assertIn("down", result)
        self.assertIn("logs", result)
        self.assertIn("ps", result)

    @patch("commands.svc.Path")
    def test_complete_svc_command_service_names(self, mock_path: Mock) -> None:
        """Test service name autocompletion."""
        ctx = Mock()
        ctx.params = {"command": ["logs"], "project": "myproject"}

        # Mock compose file
        compose_yaml = """
services:
  web:
    image: nginx
  api:
    image: api
  worker:
    image: worker
"""
        mock_file = mock_open(read_data=compose_yaml)
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path.return_value = mock_path_instance

        with patch("builtins.open", mock_file):
            result = complete_svc_command(ctx, None, "w")

        self.assertIn("web", result)
        self.assertIn("worker", result)
        self.assertNotIn("api", result)

    @patch("commands.svc.Path")
    def test_complete_svc_command_no_compose_file(self, mock_path: Mock) -> None:
        """Test service name autocompletion when compose file doesn't exist."""
        ctx = Mock()
        ctx.params = {"command": ["logs"], "project": "myproject"}

        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = False
        mock_path.return_value = mock_path_instance

        result = complete_svc_command(ctx, None, "web")

        self.assertEqual(result, [])

    @patch("commands.svc.Path")
    @patch("commands.svc.logger")
    def test_complete_svc_command_yaml_parse_error(self, mock_logger: Mock, mock_path: Mock) -> None:
        """Test service name autocompletion with YAML parse error."""
        ctx = Mock()
        ctx.params = {"command": ["logs"], "project": "myproject"}

        mock_file = mock_open(read_data="invalid: yaml: content: [")
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path.return_value = mock_path_instance

        with patch("builtins.open", mock_file):
            result = complete_svc_command(ctx, None, "web")

        # Should log debug message
        mock_logger.debug.assert_called_once()
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
