#!/usr/bin/env python3

import os
import sys
import unittest
from unittest import mock
from unittest.mock import Mock, call, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from click.testing import CliRunner

from commands.apply import apply


class TestApply(unittest.TestCase):
    """Tests for apply command"""

    def setUp(self):
        """Set up test fixtures"""
        self.runner = CliRunner()

    @patch("commands.apply.list_projects")
    @patch("commands.apply.write_upstream")
    @patch("commands.apply.subprocess.run")
    def test_apply_single_project_success(
        self, mock_subprocess: Mock, mock_write_upstream: Mock, mock_list_projects: Mock
    ) -> None:
        """Test applying a single project successfully."""
        mock_list_projects.return_value = ["myproject", "other"]
        mock_subprocess.return_value = Mock(returncode=0)

        result = self.runner.invoke(apply, ["myproject"])

        self.assertEqual(result.exit_code, 0)
        mock_write_upstream.assert_called_once_with("myproject")
        mock_subprocess.assert_called_once()

    @patch("commands.apply.list_projects")
    def test_apply_single_project_not_found(self, mock_list_projects: Mock) -> None:
        """Test applying a project that doesn't exist."""
        mock_list_projects.return_value = ["other", "another"]

        result = self.runner.invoke(apply, ["nonexistent"])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Project 'nonexistent' not found", result.output)
        self.assertIn("Available: other, another", result.output)

    @patch("commands.apply.list_projects")
    @patch("commands.apply.write_upstream")
    @patch("commands.apply.subprocess.run")
    def test_apply_single_project_deployment_failure(
        self, mock_subprocess: Mock, mock_write_upstream: Mock, mock_list_projects: Mock
    ) -> None:
        """Test handling deployment failure for single project."""
        mock_list_projects.return_value = ["myproject"]
        mock_subprocess.side_effect = lambda *args, **kwargs: (_ for _ in ()).throw(
            __import__("subprocess").CalledProcessError(1, "docker")
        )

        result = self.runner.invoke(apply, ["myproject"])

        self.assertEqual(result.exit_code, 1)
        mock_write_upstream.assert_called_once_with("myproject")

    @patch("commands.apply.list_projects")
    @patch("commands.apply.write_upstreams")
    @patch("commands.apply.subprocess.run")
    def test_apply_all_success(
        self,
        mock_subprocess: Mock,
        mock_write_upstreams: Mock,
        mock_list_projects: Mock,
    ) -> None:
        """Test applying all projects successfully."""
        mock_list_projects.return_value = ["project1", "project2"]
        mock_write_upstreams.return_value = True
        mock_subprocess.return_value = Mock(returncode=0)

        result = self.runner.invoke(apply, [])

        self.assertEqual(result.exit_code, 0)
        mock_write_upstreams.assert_called_once()
        self.assertEqual(mock_subprocess.call_count, 2)

    @patch("commands.apply.list_projects")
    @patch("commands.apply.write_upstreams")
    def test_apply_all_upstream_generation_failure(
        self, mock_write_upstreams: Mock, mock_list_projects: Mock
    ) -> None:
        """Test handling upstream generation failure."""
        mock_list_projects.return_value = ["project1", "project2"]
        mock_write_upstreams.return_value = False

        result = self.runner.invoke(apply, [])

        self.assertEqual(result.exit_code, 1)
        mock_write_upstreams.assert_called_once()

    @patch("commands.apply.list_projects")
    @patch("commands.apply.write_upstreams")
    @patch("commands.apply.subprocess.run")
    def test_apply_all_with_partial_failures(
        self,
        mock_subprocess: Mock,
        mock_write_upstreams: Mock,
        mock_list_projects: Mock,
    ) -> None:
        """Test applying all projects with some failures."""
        mock_list_projects.return_value = ["project1", "project2", "project3"]
        mock_write_upstreams.return_value = True

        # First and third succeed, second fails
        def subprocess_side_effect(*args, **kwargs):
            cmd = args[0]
            project = cmd[cmd.index("-p") + 1]
            if project == "project2":
                raise __import__("subprocess").CalledProcessError(1, "docker")
            return Mock(returncode=0)

        mock_subprocess.side_effect = subprocess_side_effect

        result = self.runner.invoke(apply, [])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Failed projects: project2", result.output)
        self.assertEqual(mock_subprocess.call_count, 3)

    @patch("commands.apply.list_projects")
    @patch("commands.apply.write_upstreams")
    @patch("commands.apply.subprocess.run")
    def test_apply_all_with_multiple_failures(
        self,
        mock_subprocess: Mock,
        mock_write_upstreams: Mock,
        mock_list_projects: Mock,
    ) -> None:
        """Test applying all projects with multiple failures."""
        mock_list_projects.return_value = ["project1", "project2", "project3"]
        mock_write_upstreams.return_value = True

        # First succeeds, second and third fail
        def subprocess_side_effect(*args, **kwargs):
            cmd = args[0]
            project = cmd[cmd.index("-p") + 1]
            if project in ["project2", "project3"]:
                raise __import__("subprocess").CalledProcessError(1, "docker")
            return Mock(returncode=0)

        mock_subprocess.side_effect = subprocess_side_effect

        result = self.runner.invoke(apply, [])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Failed projects: project2, project3", result.output)
        self.assertEqual(mock_subprocess.call_count, 3)


if __name__ == "__main__":
    unittest.main()
