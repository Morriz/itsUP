# Generated by CodiumAI
import os
import sys
import unittest
from unittest import mock
from unittest.mock import Mock

import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.data import (
    get_project,
    get_projects,
    get_service,
    upsert_env,
    upsert_project,
    write_projects,
)
from lib.models import Env, Project, Service

with open("db.yml.sample", encoding="utf-8") as f:
    _ret_db = yaml.safe_load(f)

_ret_get_projects = [
    Project(
        name="home-assistant",
        description="Home Assistant passthrough",
        domain="home.example.com",
        services=[
            Service(name="192.168.1.111", passthrough=True, port=443),
        ],
    ),
    Project(
        name="itsUP",
        description="itsUP API running on the host",
        domain="itsup.example.com",
        services=[
            Service(name="172.17.0.1", port=8888),
        ],
    ),
    Project(
        name="test",
        description="test project to demonstrate inter service connectivity",
        domain="hello.example.com",
        entrypoint="master",
        services=[
            Service(
                env={"TARGET": "cost concerned people", "INFORMANT": "http://test-informant:8080"},
                image="otomi/nodejs-helloworld:v1.2.13",
                name="master",
                volumes=["/data/bla", "/etc/dida"],
            ),
            Service(
                env={"TARGET": "boss"},
                image="otomi/nodejs-helloworld:v1.2.13",
                name="informant",
            ),
        ],
    ),
]


class TestCodeUnderTest(unittest.TestCase):

    # write all projects
    @mock.patch(
        "lib.data.yaml",
        return_value={"dump": mock.Mock()},
    )
    @mock.patch("builtins.open", new_callable=mock.mock_open)
    def test_write_projects(self, mock_open: Mock, mock_yaml: Mock) -> None:

        # Call the function under test
        write_projects(_ret_get_projects)

        mock_open.assert_called_once_with("db.yml", "w", encoding="utf-8")

        # Assert that the mock functions were called correctly
        mock_yaml.dump.assert_called_once_with(_ret_db, mock_open())

    # Get projects with filter
    @mock.patch(
        "lib.data.get_db",
        return_value=_ret_db.copy(),
    )
    def test_get_projects_with_filter(self, _: Mock) -> None:

        # Call the function under test
        result = get_projects(lambda p, s: p.name == "test" and p.entrypoint == s.name)

        # Assert the result
        expected_result = [
            Project(
                name="test",
                description="test project to demonstrate inter service connectivity",
                domain="hello.example.com",
                entrypoint="master",
                services=[
                    _ret_get_projects[2].services[0],
                ],
            ),
        ]
        self.assertEqual(result, expected_result)

    # Get all projects with no filter
    @mock.patch(
        "lib.data.get_db",
        return_value=_ret_db.copy(),
    )
    def test_get_projects_no_filter(self, mock_get_db: Mock) -> None:

        # Call the function under test
        result = get_projects()

        # Assert that the mock functions were called correctly
        mock_get_db.assert_called_once()

        # Assert the result
        self.assertEqual(result, _ret_get_projects)

    # Get a project by name that does not exist
    @mock.patch(
        "lib.data.get_projects",
        return_value=_ret_get_projects.copy(),
    )
    def test_get_nonexistent_project_by_name(self, _: Mock) -> None:

        # Call the function under test
        with self.assertRaises(ValueError):
            get_project("nonexistent_project")

    # Get a service by name that does not exist
    @mock.patch(
        "lib.data.get_project",
        return_value=_ret_get_projects.copy()[0],
    )
    def test_get_nonexistent_service_by_name(self, _: Mock) -> None:

        # Call the function under test
        with self.assertRaises(ValueError):
            get_service("project1", "nonexistent_service")

    # Upsert a project that does not exist (Fixed)
    @mock.patch("lib.data.get_projects", return_value=_ret_get_projects.copy())
    @mock.patch("lib.data.write_projects")
    def test_upsert_nonexistent_project_fixed(self, mock_write_projects: Mock, mock_get_projects: Mock) -> None:

        new_project = Project(name="new_project", domain="new_domain")
        # Call the function under test
        upsert_project(new_project)

        # Assert that the mock functions were called correctly
        mock_get_projects.assert_called_once()
        mock_write_projects.assert_called_once_with(_ret_get_projects + [new_project])

    # Upsert a project's service' env
    @mock.patch("lib.data.get_project", return_value=_ret_get_projects[2].copy())
    @mock.patch("lib.data.get_service", return_value=_ret_get_projects[2].services[1].copy())
    @mock.patch("lib.data.upsert_service")
    def test_upsert_env(self, mock_upsert_service: Mock, mock_get_service: Mock, mock_get_project: Mock) -> None:

        extra_env = Env(**{"TARGET": "sir", "x": 1, "y": 2})
        # Call the function under test
        upsert_env(project="test", service="informant", env=extra_env)

        # Assert that the mock functions were called correctly
        mock_get_project.assert_called_once()
        mock_get_service.assert_called_once()
        mock_upsert_service.assert_called_once_with(
            "test",
            Service(
                env=extra_env,
                image="otomi/nodejs-helloworld:v1.2.13",
                name="informant",
            ),
        )


if __name__ == "__main__":
    unittest.main()
