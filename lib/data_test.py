import os
import sys
import unittest
from unittest import mock
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.data import (
    expand_env_vars,
    list_projects,
    load_secrets,
    validate_all,
    validate_project,
)


class TestDataV2(unittest.TestCase):
    """Tests for V2 API functions"""

    def test_expand_env_vars_dict(self) -> None:
        """Test environment variable expansion in a dictionary."""
        secrets = {"API_KEY": "secret123", "DB_HOST": "localhost"}
        data = {"api_key": "${API_KEY}", "database": {"host": "$DB_HOST", "port": 5432}}
        result = expand_env_vars(data, secrets)
        self.assertEqual(result["api_key"], "secret123")
        self.assertEqual(result["database"]["host"], "localhost")
        self.assertEqual(result["database"]["port"], 5432)

    def test_expand_env_vars_list(self) -> None:
        """Test environment variable expansion in a list."""
        secrets = {"ENV": "production", "VERSION": "v1.0"}
        data = ["${ENV}", "$VERSION", "static"]
        result = expand_env_vars(data, secrets)
        self.assertEqual(result, ["production", "v1.0", "static"])

    def test_expand_env_vars_missing_var(self) -> None:
        """Test that missing variables raise an error."""
        secrets = {"PRESENT": "value"}
        data = "${PRESENT} and ${MISSING}"
        # Missing var raises ValueError
        with self.assertRaises(ValueError) as ctx:
            expand_env_vars(data, secrets)
        self.assertIn("MISSING", str(ctx.exception))

    def test_expand_env_vars_invalid_name(self) -> None:
        """Test that invalid variable names are not expanded."""
        secrets = {"VALID_VAR": "value"}
        # Invalid: starts with number, contains special chars
        data = "${123INVALID} ${VALID-NAME} ${VALID_VAR}"
        result = expand_env_vars(data, secrets)
        # Only VALID_VAR should be expanded
        self.assertEqual(result, "${123INVALID} ${VALID-NAME} value")

    @mock.patch("lib.data.load_env_file")
    @mock.patch("lib.data.Path")
    def test_load_secrets_with_files(self, mock_path: Mock, mock_load_env: Mock) -> None:
        """Test loading secrets from files."""
        # Mock Path behavior
        mock_secrets_dir = Mock()
        mock_path.return_value = mock_secrets_dir
        mock_secrets_dir.exists.return_value = True

        # Mock itsup.txt and project secret files
        mock_global = Mock()
        mock_global.name = "itsup.txt"
        mock_global.exists.return_value = True

        mock_project = Mock()
        mock_project.name = "myproject.txt"
        mock_project.exists.return_value = True

        # Mock __truediv__ to return correct file mocks
        def mock_truediv(_self: Mock, name: str) -> Mock:
            if "itsup" in name:
                return mock_global
            if "myproject" in name:
                return mock_project
            return Mock(exists=Mock(return_value=False))

        mock_secrets_dir.__truediv__ = mock_truediv

        # Test 1: Without project name, only itsup secrets loaded
        mock_load_env.return_value = {"GLOBAL_KEY": "global_value"}
        secrets = load_secrets()
        self.assertEqual(secrets["GLOBAL_KEY"], "global_value")

        # Test 2: With project name, only project secrets loaded (V2 behavior)
        mock_load_env.reset_mock()
        mock_load_env.return_value = {"PROJECT_KEY": "project_value"}
        secrets = load_secrets("myproject")
        self.assertEqual(secrets["PROJECT_KEY"], "project_value")
        # V2 does NOT load itsup secrets when project is specified
        self.assertNotIn("GLOBAL_KEY", secrets)

    @mock.patch("lib.data.Path")
    def test_load_secrets_no_directory(self, mock_path: Mock) -> None:
        """Test loading secrets when directory doesn't exist."""
        mock_secrets_dir = Mock()
        mock_path.return_value = mock_secrets_dir
        mock_secrets_dir.exists.return_value = False

        secrets = load_secrets()

        self.assertEqual(secrets, {})

    @mock.patch("lib.data.Path")
    def test_list_projects_empty(self, mock_path: Mock) -> None:
        """Test listing projects when directory doesn't exist."""
        mock_projects_dir = Mock()
        mock_path.return_value = mock_projects_dir
        mock_projects_dir.exists.return_value = False

        projects = list_projects()

        self.assertEqual(projects, [])

    @mock.patch("lib.data.Path")
    def test_list_projects_filters_hidden(self, mock_path: Mock) -> None:
        """Test that hidden directories are filtered out."""
        mock_projects_dir = Mock()
        mock_path.return_value = mock_projects_dir
        mock_projects_dir.exists.return_value = True

        # Create mock project directories
        mock_valid = Mock()
        mock_valid.name = "valid_project"
        mock_valid.is_dir.return_value = True
        mock_valid.__truediv__ = lambda self, name: Mock(exists=lambda: True)

        mock_hidden = Mock()
        mock_hidden.name = ".git"
        mock_hidden.is_dir.return_value = True
        mock_hidden.__truediv__ = lambda self, name: Mock(exists=lambda: True)

        mock_projects_dir.iterdir.return_value = [mock_valid, mock_hidden]

        projects = list_projects()

        # Should only include valid_project, not .git
        self.assertEqual(projects, ["valid_project"])

    @mock.patch("lib.data.load_project")
    def test_validate_project_success(self, mock_load_project: Mock) -> None:
        """Test validating a correct project."""
        mock_compose = {"services": {"web": {"image": "nginx"}}}
        mock_traefik = Mock()
        mock_traefik.ingress = [Mock(service="web")]
        mock_load_project.return_value = (mock_compose, mock_traefik)

        errors = validate_project("test_project")

        self.assertEqual(errors, [])

    @mock.patch("lib.data.load_project")
    def test_validate_project_unknown_service(self, mock_load_project: Mock) -> None:
        """Test validating a project with unknown service in traefik.yml."""
        mock_compose = {"services": {"web": {"image": "nginx"}}}
        mock_traefik = Mock()
        mock_traefik.ingress = [Mock(service="api")]  # 'api' doesn't exist
        mock_load_project.return_value = (mock_compose, mock_traefik)

        errors = validate_project("test_project")

        self.assertEqual(len(errors), 1)
        self.assertIn("unknown service", errors[0])

    @mock.patch("lib.data.load_project")
    def test_validate_project_load_error(self, mock_load_project: Mock) -> None:
        """Test validation when project fails to load."""
        mock_load_project.side_effect = FileNotFoundError("Project not found")

        errors = validate_project("missing_project")

        self.assertEqual(len(errors), 1)
        self.assertIn("Project not found", errors[0])

    @mock.patch("lib.data.list_projects")
    @mock.patch("lib.data.validate_project")
    def test_validate_all(self, mock_validate_project: Mock, mock_list_projects: Mock) -> None:
        """Test validating all projects."""
        mock_list_projects.return_value = ["project1", "project2", "project3"]
        mock_validate_project.side_effect = [[], ["error1"], []]

        results = validate_all()

        # Only project2 should be in results (has errors)
        self.assertEqual(len(results), 1)
        self.assertIn("project2", results)
        self.assertEqual(results["project2"], ["error1"])


if __name__ == "__main__":
    unittest.main()
