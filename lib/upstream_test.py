import os
import subprocess
import sys
import unittest
from io import StringIO
from unittest import TestCase, mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.data import Service
from lib.upstream import update_upstream, update_upstreams


class DirEntry:
    def __init__(self, path):
        self.path = path

    def is_dir(self):
        return True


class TestUpdateUpstream(TestCase):
    @mock.patch("subprocess.Popen")
    @mock.patch("lib.upstream.rollout_service")
    @mock.patch("lib.upstream.stream_output")
    @mock.patch("lib.upstream.get_upstream_services")
    def test_update_upstream(
        self,
        mock_get_upstream_services,
        mock_stream_output,
        mock_rollout_service,
        mock_popen,
    ):
        # Mock the get_upstream_services function
        mock_get_upstream_services.return_value = [
            Service(svc="service1", project="my_project", port=8080),
            Service(svc="service2", project="my_project", port=8080),
        ]

        # Mock the subprocess.Popen object
        mock_process = mock.Mock()
        mock_process.stdout = StringIO("Output from docker compose up")
        mock_popen.return_value = mock_process

        # Call the function under test
        update_upstream(
            "my_project",
            "service1",
            rollout=True,
        )

        # Assert that the subprocess.Popen was called with the correct arguments
        mock_popen.assert_called_once_with(
            ["docker", "compose", "up", "-d"],
            cwd="upstream/my_project",
            stdout=subprocess.PIPE,
        )

        # Assert that the output from the subprocess is printed
        self.assertEqual(
            mock_process.stdout.getvalue(), "Output from docker compose up"
        )

        # Assert that the mock_stream_output function was called
        mock_stream_output.assert_called_once_with(mock_process)

        # Assert that the rollout_service function is called correctly
        # with the correct arguments
        mock_rollout_service.assert_called_once_with("my_project", "service1")

    @mock.patch("subprocess.Popen")
    @mock.patch("lib.upstream.rollout_service")
    @mock.patch("lib.upstream.stream_output")
    def test_update_upstream_no_rollout(
        self, mock_stream_output, mock_rollout_service, mock_popen
    ):
        # Mock the subprocess.Popen object
        mock_process = mock.Mock()
        mock_process.stdout = StringIO("Output from docker compose up")
        mock_popen.return_value = mock_process

        # Mock the stream_output function
        mock_stream_output.return_value = None

        # Call the function under test
        update_upstream(
            "my_project",
            "my_service",
            rollout=False,
        )

        # Assert that the subprocess.Popen was called with the correct arguments
        mock_popen.assert_called_once_with(
            ["docker", "compose", "up", "-d"],
            cwd="upstream/my_project",
            stdout=subprocess.PIPE,
        )

        # Assert that the output from the subprocess is printed
        self.assertEqual(
            mock_process.stdout.getvalue(), "Output from docker compose up"
        )

        # Assert that the rollout_service function is not called
        mock_rollout_service.assert_not_called()

    @mock.patch("os.scandir")
    @mock.patch("lib.upstream.update_upstream")
    @mock.patch("lib.upstream.stream_output")
    def test_update_upstreams(self, _, mock_update_upstream, mock_scandir):
        mock_scandir.return_value = [DirEntry("upstream/my_project")]

        # Call the function under test
        update_upstreams()

        mock_update_upstream.assert_called_once_with(
            "my_project",
            False,
        )


if __name__ == "__main__":
    unittest.main()
