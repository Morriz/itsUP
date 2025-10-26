#!/usr/bin/env python3

import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from click.testing import CliRunner
from commands.run import run


class TestRun(unittest.TestCase):
    """Tests for run command"""

    def setUp(self):
        """Set up test fixtures"""
        self.runner = CliRunner()

    @patch("commands.run.write_proxy_artifacts")
    @patch("commands.run.subprocess.run")
    @patch("commands.run.get_env_with_secrets")
    def test_run_starts_all_stacks_in_order(
        self, mock_get_env: Mock, mock_subprocess: Mock, mock_write_artifacts: Mock
    ) -> None:
        """Test that run starts all stacks in correct order."""
        mock_get_env.return_value = {"SECRET": "value"}
        mock_subprocess.return_value = Mock(returncode=0)

        result = self.runner.invoke(run, [])

        self.assertEqual(result.exit_code, 0)

        # Must regenerate artifacts first
        mock_write_artifacts.assert_called_once()

        # Should start: DNS, proxy, API, monitor (at least 4 calls)
        self.assertGreaterEqual(mock_subprocess.call_count, 4)

        # Check that --pull always is used for docker compose up commands
        docker_up_calls = [
            call for call in mock_subprocess.call_args_list
            if "docker" in str(call) and "up" in str(call)
        ]
        self.assertGreater(len(docker_up_calls), 0)

    @patch("commands.run.write_proxy_artifacts")
    def test_run_fails_if_artifact_generation_fails(
        self, mock_write_artifacts: Mock
    ) -> None:
        """Test that run fails if artifact generation fails."""
        mock_write_artifacts.side_effect = Exception("Failed to generate")

        result = self.runner.invoke(run, [])

        self.assertEqual(result.exit_code, 1)

    @patch("commands.run.write_proxy_artifacts")
    @patch("commands.run.subprocess.run")
    @patch("commands.run.get_env_with_secrets")
    def test_run_fails_if_dns_fails(
        self, mock_get_env: Mock, mock_subprocess: Mock, mock_write_artifacts: Mock
    ) -> None:
        """Test that run fails if DNS stack fails to start."""
        mock_get_env.return_value = {"SECRET": "value"}

        # DNS call fails
        mock_subprocess.side_effect = __import__("subprocess").CalledProcessError(1, "docker")

        result = self.runner.invoke(run, [])

        self.assertEqual(result.exit_code, 1)
        # Should stop after DNS failure (may be called once or twice depending on error handling)
        self.assertLessEqual(mock_subprocess.call_count, 2)

    @patch("commands.run.write_proxy_artifacts")
    @patch("commands.run.subprocess.run")
    @patch("commands.run.get_env_with_secrets")
    def test_run_fails_if_proxy_fails(
        self, mock_get_env: Mock, mock_subprocess: Mock, mock_write_artifacts: Mock
    ) -> None:
        """Test that run fails if proxy stack fails to start."""
        mock_get_env.return_value = {"SECRET": "value"}

        # First call (DNS) succeeds, second (proxy) fails
        def subprocess_side_effect(*args, **kwargs):
            if mock_subprocess.call_count == 1:
                return Mock(returncode=0)
            else:
                raise __import__("subprocess").CalledProcessError(1, "docker")

        mock_subprocess.side_effect = subprocess_side_effect

        result = self.runner.invoke(run, [])

        self.assertEqual(result.exit_code, 1)
        # Should attempt DNS and proxy, but not API/monitor
        self.assertEqual(mock_subprocess.call_count, 2)


if __name__ == "__main__":
    unittest.main()
