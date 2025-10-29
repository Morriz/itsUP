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
    @patch("commands.apply.deploy_upstream_project")
    def test_apply_single_project_success(
        self, mock_deploy: Mock, mock_list_projects: Mock
    ) -> None:
        """Test applying a single project successfully."""
        mock_list_projects.return_value = ["myproject", "other"]

        result = self.runner.invoke(apply, ["myproject"])

        self.assertEqual(result.exit_code, 0)
        mock_deploy.assert_called_once_with("myproject")

    @patch("commands.apply.list_projects")
    def test_apply_single_project_not_found(self, mock_list_projects: Mock) -> None:
        """Test applying a project that doesn't exist."""
        mock_list_projects.return_value = ["other", "another"]

        result = self.runner.invoke(apply, ["nonexistent"])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("'nonexistent' not found", result.output)
        self.assertIn("Available: dns, proxy, other, another", result.output)

    @patch("commands.apply.list_projects")
    @patch("commands.apply.deploy_upstream_project")
    def test_apply_single_project_deployment_failure(
        self, mock_deploy: Mock, mock_list_projects: Mock
    ) -> None:
        """Test handling deployment failure for single project."""
        mock_list_projects.return_value = ["myproject"]
        mock_deploy.side_effect = Exception("Deployment failed")

        result = self.runner.invoke(apply, ["myproject"])

        self.assertEqual(result.exit_code, 1)
        mock_deploy.assert_called_once_with("myproject")

    @patch("commands.apply.deploy_proxy_stack")
    @patch("commands.apply.deploy_dns_stack")
    @patch("commands.apply.list_projects")
    @patch("commands.apply.deploy_upstream_project")
    def test_apply_all_success(
        self,
        mock_deploy: Mock,
        mock_list_projects: Mock,
        mock_dns: Mock,
        mock_proxy: Mock,
    ) -> None:
        """Test applying all projects successfully."""
        mock_list_projects.return_value = ["project1", "project2"]

        result = self.runner.invoke(apply, [])

        self.assertEqual(result.exit_code, 0)
        # Should deploy dns, proxy, + 2 projects
        self.assertEqual(mock_deploy.call_count, 2)
        mock_dns.assert_called_once()
        mock_proxy.assert_called_once()

    @patch("commands.apply.deploy_proxy_stack")
    @patch("commands.apply.deploy_dns_stack")
    @patch("commands.apply.list_projects")
    @patch("commands.apply.deploy_upstream_project")
    def test_apply_all_upstream_generation_failure(
        self,
        mock_deploy: Mock,
        mock_list_projects: Mock,
        mock_dns: Mock,
        mock_proxy: Mock,
    ) -> None:
        """Test handling upstream generation/deployment failure."""
        mock_list_projects.return_value = ["project1", "project2"]
        mock_deploy.side_effect = Exception("Generation failed")

        result = self.runner.invoke(apply, [])

        self.assertEqual(result.exit_code, 1)


if __name__ == "__main__":
    unittest.main()
