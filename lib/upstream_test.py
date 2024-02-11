import os
import sys
import unittest
from unittest import TestCase, mock
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.data import Service
from lib.upstream import update_upstream, update_upstreams


# pylint: disable=too-few-public-methods
class DirEntry:
    def __init__(self, path):
        self.path = path

    def is_dir(self):
        return True


# pylint: enable=too-few-public-methods


class TestUpdateUpstream(TestCase):
    @mock.patch("lib.upstream.rollout_service")
    @mock.patch("lib.upstream.run_command")
    @mock.patch("lib.upstream.get_upstream_services")
    def test_update_upstream(
        self,
        mock_get_upstream_services: Mock,
        mock_run_command: Mock,
        mock_rollout_service: Mock,
    ):
        # Mock the get_upstream_services function
        mock_get_upstream_services.return_value = [
            Service(svc="service1", project="my_project", port=8080),
            Service(svc="service2", project="my_project", port=8080),
        ]

        # Call the function under test
        update_upstream(
            "my_project",
            "service1",
            rollout=True,
        )

        # Assert that the subprocess.Popen was called with the correct arguments
        mock_run_command.assert_called_once_with(
            ["docker", "compose", "up", "-d"],
            cwd="upstream/my_project",
        )

        # Assert that the rollout_service function is called correctly
        # with the correct arguments
        mock_rollout_service.assert_called_once_with("my_project", "service1")

    @mock.patch("lib.upstream.rollout_service")
    @mock.patch("lib.upstream.run_command")
    def test_update_upstream_no_rollout(
        self, mock_run_command: Mock, mock_rollout_service: Mock
    ):

        # Call the function under test
        update_upstream(
            "my_project",
            "my_service",
            rollout=False,
        )

        mock_run_command.assert_called_once_with(
            ["docker", "compose", "up", "-d"],
            cwd="upstream/my_project",
        )

        # Assert that the rollout_service function is not called
        mock_rollout_service.assert_not_called()

    @mock.patch("os.scandir")
    @mock.patch("lib.upstream.update_upstream")
    @mock.patch("lib.upstream.run_command")
    def test_update_upstreams(self, _, mock_update_upstream: Mock, mock_scandir: Mock):
        mock_scandir.return_value = [DirEntry("upstream/my_project")]

        # Call the function under test
        update_upstreams()

        mock_update_upstream.assert_called_once_with(
            "my_project",
            False,
        )


if __name__ == "__main__":
    unittest.main()
