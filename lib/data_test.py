import os
import sys
import unittest
from unittest import mock
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.data import (
    expand_env_vars,
    list_projects,
    load_infrastructure,
    load_project,
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
        """Test that missing variables are left unchanged."""
        secrets = {"PRESENT": "value"}
        data = "${PRESENT} and ${MISSING}"
        result = expand_env_vars(data, secrets)
        # Missing var is left as-is
        self.assertEqual(result, "value and ${MISSING}")

    def test_expand_env_vars_invalid_name(self) -> None:
        """Test that invalid variable names are not expanded."""
        secrets = {"VALID_VAR": "value"}
        # Invalid: starts with number, contains special chars
        data = "${123INVALID} ${VALID-NAME} ${VALID_VAR}"
        result = expand_env_vars(data, secrets)
        # Only VALID_VAR should be expanded
        self.assertEqual(result, "${123INVALID} ${VALID-NAME} value")

    @mock.patch("lib.data.Path")
    @mock.patch("lib.data.dotenv_values")
    def test_load_secrets_with_files(self, mock_dotenv: Mock, mock_path: Mock) -> None:
        """Test loading secrets from files."""
        # Mock Path behavior
        mock_secrets_dir = Mock()
        mock_path.return_value = mock_secrets_dir
        mock_secrets_dir.exists.return_value = True

        # Mock global.txt and other secret files
        mock_global = Mock()
        mock_global.name = "global.txt"
        mock_project_secret = Mock()
        mock_project_secret.name = "myproject.txt"

        mock_secrets_dir.__truediv__ = lambda self, name: mock_global if name == "global.txt" else Mock()
        mock_secrets_dir.glob.return_value = [mock_global, mock_project_secret]
        mock_global.exists.return_value = True

        # Mock dotenv_values returns
        mock_dotenv.side_effect = [{"GLOBAL_KEY": "global_value"}, {"PROJECT_KEY": "project_value"}]

        secrets = load_secrets()

        self.assertEqual(secrets["GLOBAL_KEY"], "global_value")
        self.assertEqual(secrets["PROJECT_KEY"], "project_value")

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
