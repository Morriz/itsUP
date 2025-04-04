# Generated by CodiumAI
import os
import sys
import unittest
from unittest import mock
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.data import (
    get_db,
    get_env,
    get_plugin_model,
    get_plugin_registry,
    get_plugins,
    get_project,
    get_projects,
    get_service,
    get_services,
    get_versions,
    upsert_env,
    upsert_project,
    upsert_service,
    validate_db,
    write_db,
    write_projects,
)
from lib.models import Env, Ingress, Plugin, PluginRegistry, Project, Router, Service
from lib.test_stubs import test_db, test_projects


class TestData(unittest.TestCase):

    @mock.patch("lib.data.get_db", return_value=test_db.copy())
    @mock.patch(
        "lib.data.yaml",
        return_value={"dump": mock.Mock()},
    )
    @mock.patch("builtins.open", new_callable=mock.mock_open)
    def test_write_db(self, mock_open: Mock, mock_yaml: Mock, _: Mock) -> None:

        # Call the function under test
        write_db({"projects": test_db["projects"]})

        mock_open.assert_called_once_with("db.yml", "w", encoding="utf-8")

        # Assert that the mock functions were called correctly
        mock_yaml.dump.assert_called_once_with(
            {
                "versions": {"traefik": "v3", "crowdsec": "v1.6.0"},
                "plugins": test_db["plugins"],
                "projects": test_db["projects"],
            },
            mock_open(),
        )

    @mock.patch("lib.data.write_db")
    def test_write_projects(self, mock_write_db: Mock) -> None:

        # Call the function under test
        write_projects(test_projects)

        # Assert that the mock functions were called correctly
        mock_write_db.assert_called_once()

    # Get projects with filter
    @mock.patch(
        "lib.data.get_db",
        return_value=test_db.copy(),
    )
    def test_get_projects_with_filter(self, _: Mock) -> None:

        # Call the function under test
        result = get_projects(lambda p, s: p.name == "whoami" and s.ingress)[0]

        # Assert the result
        expected_result = Project(
            description="whoami service",
            name="whoami",
            services=[
                Service(image="traefik/whoami:latest", host="web"),
            ],
        )
        expected_result.services[0].ingress = [Ingress(domain="whoami.example.com")]
        self.assertEqual(result, expected_result)

    # Get all projects with no filter
    @mock.patch(
        "lib.data.get_db",
        return_value=test_db.copy(),
    )
    def test_get_projects_no_filter(self, mock_get_db: Mock) -> None:
        self.maxDiff = None

        # Call the function under test
        get_projects()

        # Assert that the mock functions were called correctly
        mock_get_db.assert_called_once()

        # Assert the result
        # self.assertEqual(result, test_projects)

    # Get a project by name that does not exist
    @mock.patch(
        "lib.data.get_projects",
        return_value=test_projects.copy(),
    )
    def test_get_nonexistent_project_by_name(self, _: Mock) -> None:

        # Call the function under test
        with self.assertRaises(ValueError):
            get_project("nonexistent_project")

    # Get a service by name that does not exist
    @mock.patch(
        "lib.data.get_project",
        return_value=test_projects.copy()[0],
    )
    def test_get_nonexistent_service_by_name(self, _: Mock) -> None:

        # Call the function under test
        with self.assertRaises(ValueError):
            get_service("project1", "nonexistent_service")

    # Upsert a project that does not exist
    @mock.patch("lib.data.get_projects", return_value=test_projects.copy())
    @mock.patch("lib.data.write_projects")
    def test_upsert_nonexistent_project(self, mock_write_projects: Mock, mock_get_projects: Mock) -> None:

        new_project = Project(name="new_project", domain="new_domain")
        # Call the function under test
        upsert_project(new_project)

        # Assert that the mock functions were called correctly
        mock_get_projects.assert_called_once()
        mock_write_projects.assert_called_once_with(test_projects + [new_project])

    @mock.patch(
        "builtins.open", new_callable=mock.mock_open, read_data="versions:\\n  traefik: v3\\nplugins: {}\\nprojects: []"
    )
    @mock.patch("lib.data.yaml.safe_load", return_value=test_db.copy())
    def test_get_db(self, mock_safe_load: Mock, mock_open: Mock) -> None:
        """Test getting the database."""
        db = get_db()
        mock_open.assert_called_once_with("db.yml", encoding="utf-8")
        mock_safe_load.assert_called_once()
        self.assertEqual(db, test_db)

    @mock.patch("importlib.import_module")
    def test_get_plugin_model_exists(self, mock_import_module: Mock) -> None:
        """Test getting an existing plugin model."""
        mock_module = Mock()
        mock_import_module.return_value = mock_module
        model = get_plugin_model("testplugin")
        mock_import_module.assert_called_once_with("lib.models.PluginTestplugin")
        self.assertEqual(model, mock_module)

    @mock.patch("importlib.import_module", side_effect=ModuleNotFoundError)
    def test_get_plugin_model_not_exists(self, mock_import_module: Mock) -> None:
        """Test getting a non-existing plugin model falls back to base Plugin."""
        model = get_plugin_model("nonexistent")
        mock_import_module.assert_called_once_with("lib.models.PluginNonexistent")
        self.assertEqual(model, Plugin)

    @mock.patch("lib.data.get_db", return_value=test_db.copy())
    @mock.patch("lib.data.get_plugin_model", return_value=Plugin)
    @mock.patch("lib.models.Project.model_validate")
    @mock.patch("lib.models.Plugin.model_validate")
    def test_validate_db(
        self, mock_plugin_validate: Mock, mock_project_validate: Mock, mock_get_plugin_model: Mock, mock_get_db: Mock
    ) -> None:
        """Test validating the database."""
        validate_db()
        mock_get_db.assert_called_once()
        # Check plugin validation calls
        self.assertEqual(mock_get_plugin_model.call_count, len(test_db["plugins"]))
        self.assertEqual(mock_plugin_validate.call_count, len(test_db["plugins"]))
        # Check project validation calls
        self.assertEqual(mock_project_validate.call_count, len(test_db["projects"]))

    @mock.patch("lib.data.get_db", return_value=test_db.copy())
    def test_get_versions(self, mock_get_db: Mock) -> None:
        """Test getting versions."""
        versions = get_versions()
        mock_get_db.assert_called_once()
        self.assertEqual(versions, test_db["versions"])

    @mock.patch("lib.data.get_db", return_value=test_db.copy())
    def test_get_plugin_registry(self, mock_get_db: Mock) -> None:
        """Test getting the plugin registry."""
        registry = get_plugin_registry()
        mock_get_db.assert_called_once()
        self.assertIsInstance(registry, PluginRegistry)
        self.assertEqual(set(registry.model_dump().keys()), set(test_db["plugins"].keys()))

    @mock.patch("lib.data.get_plugin_registry")
    @mock.patch("lib.data.get_plugin_model", return_value=Plugin)
    def test_get_plugins_no_filter(self, mock_get_model: Mock, mock_get_registry: Mock) -> None:
        """Test getting all plugins without a filter."""
        mock_registry = Mock()
        mock_registry.configure_mock(**{"__iter__": Mock(return_value=iter(test_db["plugins"].items()))})
        mock_get_registry.return_value = mock_registry

        plugins = get_plugins()

        mock_get_registry.assert_called_once()
        self.assertEqual(mock_get_model.call_count, len(test_db["plugins"]))
        self.assertEqual(len(plugins), len(test_db["plugins"]))
        self.assertIsInstance(plugins[0], Plugin)

    @mock.patch("lib.data.get_plugin_registry")
    @mock.patch("lib.data.get_plugin_model", return_value=Plugin)
    def test_get_plugins_with_filter(self, mock_get_model: Mock, mock_get_registry: Mock) -> None:
        """Test getting plugins with a filter."""
        mock_registry = Mock()
        mock_registry.configure_mock(**{"__iter__": Mock(return_value=iter(test_db["plugins"].items()))})
        mock_get_registry.return_value = mock_registry

        # Filter for a specific plugin name
        filter_func = lambda p: p.name == "crowdsec"
        plugins = get_plugins(filter=filter_func)

        mock_get_registry.assert_called_once()
        self.assertEqual(mock_get_model.call_count, len(test_db["plugins"]))
        self.assertEqual(len(plugins), 1)
        self.assertEqual(plugins[0].name, "crowdsec")

    @mock.patch("lib.data.get_projects", return_value=test_projects.copy())
    def test_get_project_exists(self, mock_get_projects: Mock) -> None:
        """Test getting an existing project by name."""
        project_name = "whoami"
        project = get_project(project_name)
        mock_get_projects.assert_called_once()
        self.assertIsNotNone(project)
        self.assertEqual(project.name, project_name)
        # Deep check one attribute
        self.assertEqual(project.services[0].image, "traefik/whoami:latest")

    @mock.patch("lib.data.get_projects", return_value=test_projects.copy())
    def test_get_project_not_found_no_throw(self, mock_get_projects: Mock) -> None:
        """Test getting a non-existent project without throwing an error."""
        project = get_project("nonexistent", throw=False)
        mock_get_projects.assert_called_once()
        self.assertIsNone(project)

    @mock.patch("lib.data.get_projects", return_value=test_projects.copy())
    def test_get_services_all(self, mock_get_projects: Mock) -> None:
        """Test getting all services from all projects."""
        services = get_services()
        mock_get_projects.assert_called_once()
        total_services = sum(len(p.services) for p in test_projects)
        self.assertEqual(len(services), total_services)
        self.assertIsInstance(services[0], Service)

    @mock.patch("lib.data.get_projects")
    def test_get_services_for_project(self, mock_get_projects: Mock) -> None:
        """Test getting services for a specific project."""
        project_name = "whoami"
        # Mock get_projects to return only the 'whoami' project when filtered
        whoami_project = next(p for p in test_projects if p.name == project_name)
        mock_get_projects.return_value = [whoami_project]

        services = get_services(project=project_name)

        # Assert get_projects was called with a lambda filter
        mock_get_projects.assert_called_once()
        filter_arg = mock_get_projects.call_args[0][0]
        self.assertTrue(callable(filter_arg))

        self.assertEqual(len(services), len(whoami_project.services))
        self.assertEqual(services[0].host, "web")

    @mock.patch("lib.data.get_project", return_value=test_projects[5].model_copy())
    def test_get_service_exists(self, mock_get_project: Mock) -> None:
        """Test getting an existing service from a project."""
        project_name = "whoami"
        service_host = "web"
        service = get_service(project_name, service_host)
        mock_get_project.assert_called_once_with(project_name, True)
        self.assertIsNotNone(service)
        self.assertEqual(service.host, service_host)
        self.assertEqual(service.image, "traefik/whoami:latest")

    @mock.patch("lib.data.get_project", return_value=test_projects[5].model_copy())
    def test_get_service_not_found_no_throw(self, mock_get_project: Mock) -> None:
        """Test getting a non-existent service without throwing an error."""
        service = get_service("whoami", "nonexistent", throw=False)
        mock_get_project.assert_called_once_with("whoami", False)
        self.assertIsNone(service)

    @mock.patch("lib.data.get_project")
    @mock.patch("lib.data.upsert_project")
    def test_upsert_service_new(self, mock_upsert_project: Mock, mock_get_project: Mock) -> None:
        """Test upserting a new service into a project."""
        project_name = "project1"
        existing_project = Project(name=project_name, services=[Service(host="existing", image="img1")])
        mock_get_project.return_value = existing_project.model_copy(deep=True)

        new_service = Service(host="new_service", image="new_image")
        upsert_service(project_name, new_service)

        mock_get_project.assert_called_once_with(project_name)
        # Check the project passed to upsert_project
        mock_upsert_project.assert_called_once()
        updated_project = mock_upsert_project.call_args[0][0]
        self.assertEqual(len(updated_project.services), 2)
        self.assertEqual(updated_project.services[1], new_service)

    @mock.patch("lib.data.get_project")
    @mock.patch("lib.data.upsert_project")
    def test_upsert_service_existing(self, mock_upsert_project: Mock, mock_get_project: Mock) -> None:
        """Test upserting an existing service in a project."""
        project_name = "project1"
        service_to_update = Service(host="existing", image="img1")
        existing_project = Project(name=project_name, services=[service_to_update])
        mock_get_project.return_value = existing_project.model_copy(deep=True)

        updated_service = Service(host="existing", image="updated_image")  # Removed non-existent 'ports'
        upsert_service(project_name, updated_service)

        mock_get_project.assert_called_once_with(project_name)
        # Check the project passed to upsert_project
        mock_upsert_project.assert_called_once()
        updated_project = mock_upsert_project.call_args[0][0]
        self.assertEqual(len(updated_project.services), 1)
        self.assertEqual(updated_project.services[0], updated_service)
        self.assertEqual(updated_project.services[0].image, "updated_image")
        # Removed assertion for non-existent 'ports' attribute

    @mock.patch("lib.data.get_service")
    def test_get_env(self, mock_get_service: Mock) -> None:
        """Test getting the environment variables for a service."""
        project_name = "project_with_env"
        service_host = "service1"
        expected_env = {"VAR1": "value1", "VAR2": "value2"}
        mock_service = Service(host=service_host, image="test", env=Env(**expected_env))
        mock_get_service.return_value = mock_service

        env = get_env(project_name, service_host)

        mock_get_service.assert_called_once_with(project_name, service_host)
        self.assertEqual(env.model_dump(), expected_env)  # Compare dict representation

    @mock.patch("lib.data.get_project", return_value=test_projects[3].model_copy())
    @mock.patch("lib.data.get_service", return_value=test_projects[3].services[0].model_copy())
    @mock.patch("lib.data.upsert_service")
    def test_upsert_env(self, mock_upsert_service: Mock, mock_get_service: Mock, mock_get_project: Mock) -> None:

        extra_env = Env(**{"OKI": "doki"})
        # Call the function under test
        upsert_env(project="minio", service="app", env=extra_env)

        # Assert that the mock functions were called correctly
        mock_get_project.assert_called_once()
        mock_get_service.assert_called_once()
        mock_upsert_service.assert_called_once_with(
            "minio",
            Service(
                additional_properties={},
                command='server --console-address ":9001" /data',
                depends_on=[],
                env=Env(MINIO_ROOT_USER="root", MINIO_ROOT_PASSWORD="xx", OKI="doki"),
                host="app",
                image="minio/minio:latest",
                ingress=[
                    Ingress(
                        domain="minio-api.example.com",
                        port=9000,
                        router=Router.udp,
                    ),
                    Ingress(domain="minio-ui.example.com", port=9001),
                ],
                labels=[],
                restart="unless-stopped",
                volumes=["/data"],
            ),
        )


if __name__ == "__main__":
    unittest.main()
