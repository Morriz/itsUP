import os
import sys
import unittest
from unittest import mock
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.data import (
    expand_env_vars,
    list_projects,
    list_projects_topo,
    load_secrets,
    validate_all,
    validate_project,
)
from lib.models import Ingress, TraefikConfig


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

    @mock.patch("lib.data.load_encrypted_env")
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

    @mock.patch("lib.data.logger")
    @mock.patch("lib.data.Path")
    def test_load_secrets_no_directory(self, mock_path: Mock, mock_logger: Mock) -> None:
        """Test loading secrets when directory doesn't exist."""
        mock_secrets_dir = Mock()
        mock_path.return_value = mock_secrets_dir
        mock_secrets_dir.exists.return_value = False

        secrets = load_secrets()

        self.assertEqual(secrets, {})
        # Verify warning was logged (but suppressed from output)
        mock_logger.warning.assert_called_once()

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
        mock_traefik.ingress = [Mock(service="web", ipv4_address=None)]
        mock_traefik.egress = []
        mock_load_project.return_value = (mock_compose, mock_traefik)

        errors = validate_project("test_project")

        self.assertEqual(errors, [])

    @mock.patch("lib.data.load_project")
    def test_validate_project_unknown_service(self, mock_load_project: Mock) -> None:
        """Test validating a project with unknown service in traefik.yml."""
        mock_compose = {"services": {"web": {"image": "nginx"}}}
        mock_traefik = Mock()
        mock_traefik.ingress = [Mock(service="api", ipv4_address=None)]  # 'api' doesn't exist
        mock_traefik.egress = []
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
    @mock.patch("lib.data.load_project")
    def test_validate_project_egress_valid(self, mock_load_project: Mock, mock_list_projects: Mock) -> None:
        """Test validating a project with valid egress declarations."""
        mock_compose = {"services": {"web": {"image": "nginx"}}}
        mock_traefik = Mock()
        mock_traefik.ingress = []
        mock_traefik.egress = ["target-project:redis"]

        # Mock for current project
        mock_target_compose = {"services": {"target-project-redis": {"image": "redis"}}}
        mock_target_traefik = Mock()
        mock_target_traefik.egress = []

        mock_load_project.side_effect = [
            (mock_compose, mock_traefik),  # Current project
            (mock_target_compose, mock_target_traefik),  # Target project
        ]
        mock_list_projects.return_value = ["test-project", "target-project"]

        errors = validate_project("test-project")

        self.assertEqual(errors, [])

    @mock.patch("lib.data.load_project")
    def test_validate_project_egress_invalid_format(self, mock_load_project: Mock) -> None:
        """Test validation with invalid egress format (missing colon)."""
        mock_compose = {"services": {"web": {"image": "nginx"}}}
        mock_traefik = Mock()
        mock_traefik.ingress = []
        mock_traefik.egress = ["invalid-format"]  # Missing colon
        mock_load_project.return_value = (mock_compose, mock_traefik)

        errors = validate_project("test-project")

        self.assertEqual(len(errors), 1)
        self.assertIn("must be in format: project:service", errors[0])

    @mock.patch("lib.data.list_projects")
    @mock.patch("lib.data.load_project")
    def test_validate_project_egress_project_not_found(self, mock_load_project: Mock, mock_list_projects: Mock) -> None:
        """Test validation when egress target project doesn't exist."""
        mock_compose = {"services": {"web": {"image": "nginx"}}}
        mock_traefik = Mock()
        mock_traefik.ingress = []
        mock_traefik.egress = ["nonexistent:redis"]
        mock_load_project.return_value = (mock_compose, mock_traefik)
        mock_list_projects.return_value = ["test-project"]  # 'nonexistent' not in list

        errors = validate_project("test-project")

        self.assertEqual(len(errors), 1)
        self.assertIn("target project 'nonexistent' not found", errors[0])

    @mock.patch("lib.data.list_projects")
    @mock.patch("lib.data.load_project")
    def test_validate_project_egress_service_not_found(self, mock_load_project: Mock, mock_list_projects: Mock) -> None:
        """Test validation when egress target service doesn't exist."""
        mock_compose = {"services": {"web": {"image": "nginx"}}}
        mock_traefik = Mock()
        mock_traefik.ingress = []
        mock_traefik.egress = ["target-project:nonexistent"]

        # Target project has different services
        mock_target_compose = {"services": {"target-project-redis": {"image": "redis"}}}
        mock_target_traefik = Mock()
        mock_target_traefik.egress = []

        mock_load_project.side_effect = [
            (mock_compose, mock_traefik),  # Current project
            (mock_target_compose, mock_target_traefik),  # Target project
        ]
        mock_list_projects.return_value = ["test-project", "target-project"]

        errors = validate_project("test-project")

        self.assertEqual(len(errors), 1)
        self.assertIn("target service 'nonexistent' not found", errors[0])

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

    @mock.patch("lib.data.load_project")
    def test_validate_project_ipv4_address_valid(self, mock_load_project: Mock) -> None:
        """A static proxynet IP within the subnet validates cleanly."""
        compose = {"services": {"adguard-app": {"image": "adguard/adguardhome"}}}
        traefik = TraefikConfig(
            ingress=[Ingress(service="adguard-app", domain="adguard.example.com", ipv4_address="172.20.0.252")]
        )
        mock_load_project.return_value = (compose, traefik)

        self.assertEqual(validate_project("adguard"), [])

    # NOTE: these tests prove the validator FIRES for each failure mode but
    # do not pin WHICH error message is produced — asserting the prose would
    # violate the testing policy's substring-on-string-content ban. When
    # validate_project gains structured errors (typed objects), upgrade these
    # to assert error.kind == "out_of_subnet" etc.

    @mock.patch("lib.data.load_project")
    def test_validate_project_ipv4_address_out_of_subnet(self, mock_load_project: Mock) -> None:
        """A static IP outside the proxynet subnet is rejected."""
        compose = {"services": {"web": {"image": "nginx"}}}
        traefik = TraefikConfig(ingress=[Ingress(service="web", domain="x.example.com", ipv4_address="10.0.0.5")])
        mock_load_project.return_value = (compose, traefik)

        self.assertEqual(len(validate_project("test-project")), 1)

    @mock.patch("lib.data.load_project")
    def test_validate_project_ipv4_address_reserved(self, mock_load_project: Mock) -> None:
        """The honeypot/gateway IPs are reserved and rejected."""
        compose = {"services": {"web": {"image": "nginx"}}}
        traefik = TraefikConfig(ingress=[Ingress(service="web", domain="x.example.com", ipv4_address="172.20.0.253")])
        mock_load_project.return_value = (compose, traefik)

        self.assertEqual(len(validate_project("test-project")), 1)

    @mock.patch("lib.data.load_project")
    def test_validate_project_ipv4_address_conflict_same_service(self, mock_load_project: Mock) -> None:
        """Two ingress rows pinning the same service to different IPs is a conflict."""
        compose = {"services": {"web": {"image": "nginx"}}}
        traefik = TraefikConfig(
            ingress=[
                Ingress(service="web", domain="a.example.com", ipv4_address="172.20.0.10"),
                Ingress(service="web", domain="b.example.com", ipv4_address="172.20.0.11"),
            ]
        )
        mock_load_project.return_value = (compose, traefik)

        self.assertEqual(len(validate_project("test-project")), 1)

    @mock.patch("lib.data.list_projects")
    @mock.patch("lib.data.load_project")
    def test_validate_all_ipv4_address_cross_project_collision(
        self, mock_load_project: Mock, mock_list_projects: Mock
    ) -> None:
        """The same proxynet IP claimed by two projects is flagged."""
        compose_a = {"services": {"a": {"image": "nginx"}}}
        traefik_a = TraefikConfig(ingress=[Ingress(service="a", domain="a.example.com", ipv4_address="172.20.0.50")])
        compose_b = {"services": {"b": {"image": "nginx"}}}
        traefik_b = TraefikConfig(ingress=[Ingress(service="b", domain="b.example.com", ipv4_address="172.20.0.50")])

        mock_list_projects.return_value = ["proj-a", "proj-b"]
        # validate_project loads once per project, then validate_all loads once more per project
        mock_load_project.side_effect = [
            (compose_a, traefik_a),
            (compose_b, traefik_b),
            (compose_a, traefik_a),
            (compose_b, traefik_b),
        ]

        results = validate_all()

        # proj-b is the second project to claim the IP, so the collision
        # detection appends an error to its result list. (See note above on
        # why the prose itself is not asserted.)
        self.assertIn("proj-b", results)
        self.assertTrue(results["proj-b"])

    @mock.patch("lib.data.load_project")
    @mock.patch("lib.data.list_projects")
    def test_list_projects_topo_empty(self, mock_list_projects: Mock, mock_load_project: Mock) -> None:
        """Empty project set yields empty order."""
        mock_list_projects.return_value = []
        self.assertEqual(list_projects_topo(), [])
        mock_load_project.assert_not_called()

    @mock.patch("lib.data.load_project")
    @mock.patch("lib.data.list_projects")
    def test_list_projects_topo_independent_alphabetical(
        self, mock_list_projects: Mock, mock_load_project: Mock
    ) -> None:
        """Projects without egress edges sort alphabetically (deterministic)."""
        mock_list_projects.return_value = ["c", "a", "b"]
        mock_load_project.return_value = ({}, TraefikConfig(egress=[]))

        self.assertEqual(list_projects_topo(), ["a", "b", "c"])

    @mock.patch("lib.data.load_project")
    @mock.patch("lib.data.list_projects")
    def test_list_projects_topo_linear_dependency(self, mock_list_projects: Mock, mock_load_project: Mock) -> None:
        """`a` egress→`b` puts b before a despite a coming first alphabetically."""
        mock_list_projects.return_value = ["a", "b"]
        mock_load_project.side_effect = lambda name: (
            {},
            TraefikConfig(egress=["b:svc"] if name == "a" else []),
        )

        self.assertEqual(list_projects_topo(), ["b", "a"])

    @mock.patch("lib.data.load_project")
    @mock.patch("lib.data.list_projects")
    def test_list_projects_topo_diamond(self, mock_list_projects: Mock, mock_load_project: Mock) -> None:
        """`c` depends on `a` and `b`; both deploy first (alphabetical), then `c`."""
        mock_list_projects.return_value = ["a", "b", "c"]

        def loader(name: str) -> tuple[dict[str, object], TraefikConfig]:
            if name == "c":
                return ({}, TraefikConfig(egress=["a:svc", "b:svc"]))
            return ({}, TraefikConfig(egress=[]))

        mock_load_project.side_effect = loader

        self.assertEqual(list_projects_topo(), ["a", "b", "c"])

    @mock.patch("lib.data.load_project")
    @mock.patch("lib.data.list_projects")
    def test_list_projects_topo_cycle_falls_back_alphabetical(
        self, mock_list_projects: Mock, mock_load_project: Mock
    ) -> None:
        """An egress cycle (a↔b) is invalid config; fall back to alphabetical, do not raise."""
        mock_list_projects.return_value = ["a", "b"]
        mock_load_project.side_effect = lambda name: (
            {},
            TraefikConfig(egress=["b:svc"] if name == "a" else ["a:svc"]),
        )

        self.assertEqual(list_projects_topo(), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
