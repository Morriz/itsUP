#!/usr/bin/env python3

import os
import sys
import unittest
from unittest import mock
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from click.testing import CliRunner

from commands.validate import validate


class TestValidate(unittest.TestCase):
    """Tests for validate command"""

    def setUp(self):
        """Set up test fixtures"""
        self.runner = CliRunner()

    @patch("commands.validate.validate_project")
    def test_validate_single_project_success(self, mock_validate_project: Mock) -> None:
        """Test validating a single project successfully."""
        mock_validate_project.return_value = []

        result = self.runner.invoke(validate, ["myproject"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("✓ myproject: valid", result.output)
        mock_validate_project.assert_called_once_with("myproject")

    @patch("commands.validate.validate_project")
    def test_validate_single_project_with_errors(self, mock_validate_project: Mock) -> None:
        """Test validating a single project with errors."""
        mock_validate_project.return_value = ["Error 1", "Error 2"]

        result = self.runner.invoke(validate, ["myproject"])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("✗ myproject: 2 error(s)", result.output)
        self.assertIn("- Error 1", result.output)
        self.assertIn("- Error 2", result.output)
        mock_validate_project.assert_called_once_with("myproject")

    @patch("commands.validate.validate_project")
    def test_validate_single_project_with_single_error(self, mock_validate_project: Mock) -> None:
        """Test validating a single project with one error."""
        mock_validate_project.return_value = ["Missing required field"]

        result = self.runner.invoke(validate, ["myproject"])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("✗ myproject: 1 error(s)", result.output)
        self.assertIn("- Missing required field", result.output)

    @patch("commands.validate.validate_all")
    def test_validate_all_success(self, mock_validate_all: Mock) -> None:
        """Test validating all projects successfully."""
        mock_validate_all.return_value = {}

        result = self.runner.invoke(validate, [])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("✓ All projects valid", result.output)
        mock_validate_all.assert_called_once()

    @patch("commands.validate.validate_all")
    def test_validate_all_with_errors(self, mock_validate_all: Mock) -> None:
        """Test validating all projects with errors."""
        mock_validate_all.return_value = {
            "project1": ["Error 1", "Error 2"],
            "project2": ["Error 3"],
        }

        result = self.runner.invoke(validate, [])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("✗ 2 project(s) with errors:", result.output)
        self.assertIn("project1:", result.output)
        self.assertIn("- Error 1", result.output)
        self.assertIn("- Error 2", result.output)
        self.assertIn("project2:", result.output)
        self.assertIn("- Error 3", result.output)
        mock_validate_all.assert_called_once()

    @patch("commands.validate.validate_all")
    def test_validate_all_with_single_project_error(self, mock_validate_all: Mock) -> None:
        """Test validating all projects with one project having errors."""
        mock_validate_all.return_value = {
            "project1": ["Configuration issue"],
        }

        result = self.runner.invoke(validate, [])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("✗ 1 project(s) with errors:", result.output)
        self.assertIn("project1:", result.output)
        self.assertIn("- Configuration issue", result.output)

    @patch("commands.validate.validate_all")
    def test_validate_all_with_multiple_errors_per_project(self, mock_validate_all: Mock) -> None:
        """Test validating all projects with multiple errors per project."""
        mock_validate_all.return_value = {
            "project1": ["Error A", "Error B", "Error C"],
            "project2": ["Error D", "Error E"],
            "project3": ["Error F"],
        }

        result = self.runner.invoke(validate, [])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("✗ 3 project(s) with errors:", result.output)

        # Verify all projects and errors are listed
        for project in ["project1", "project2", "project3"]:
            self.assertIn(f"{project}:", result.output)

        for error in ["Error A", "Error B", "Error C", "Error D", "Error E", "Error F"]:
            self.assertIn(f"- {error}", result.output)


if __name__ == "__main__":
    unittest.main()
