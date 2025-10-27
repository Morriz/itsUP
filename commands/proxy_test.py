#!/usr/bin/env python3

import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from click.testing import CliRunner
from commands.proxy import proxy


class TestProxy(unittest.TestCase):
    """Tests for proxy command"""

    def setUp(self):
        """Set up test fixtures"""
        self.runner = CliRunner()

    def test_proxy_help(self) -> None:
        """Test proxy help command."""
        result = self.runner.invoke(proxy, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Proxy stack management", result.output)

    @patch("commands.proxy.deploy_proxy_stack")
    def test_proxy_up_regenerates_config(
        self, mock_deploy: Mock
    ) -> None:
        """Test that proxy up uses smart deployment."""
        result = self.runner.invoke(proxy, ["up"])

        self.assertEqual(result.exit_code, 0)
        # Should call deploy with no service arg
        mock_deploy.assert_called_once_with(service=None)

    @patch("commands.proxy.deploy_proxy_stack")
    def test_proxy_up_single_service(
        self, mock_deploy: Mock
    ) -> None:
        """Test starting single proxy service."""
        result = self.runner.invoke(proxy, ["up", "traefik"])

        self.assertEqual(result.exit_code, 0)
        mock_deploy.assert_called_once_with(service="traefik")

    @patch("commands.proxy.deploy_proxy_stack")
    def test_proxy_up_artifacts_failure(
        self, mock_deploy: Mock
    ) -> None:
        """Test that proxy up fails if deployment fails."""
        mock_deploy.side_effect = Exception("Failed to deploy")

        result = self.runner.invoke(proxy, ["up"])

        self.assertEqual(result.exit_code, 1)
        mock_deploy.assert_called_once_with(service=None)

    @patch("commands.proxy.subprocess.run")
    @patch("commands.proxy.get_env_with_secrets")
    def test_proxy_down(self, mock_get_env: Mock, mock_subprocess: Mock) -> None:
        """Test proxy down command."""
        mock_get_env.return_value = {"SECRET": "value"}
        mock_subprocess.return_value = Mock(returncode=0)

        result = self.runner.invoke(proxy, ["down"])

        self.assertEqual(result.exit_code, 0)
        cmd = mock_subprocess.call_args[0][0]
        self.assertIn("down", cmd)

    @patch("commands.proxy.subprocess.run")
    @patch("commands.proxy.get_env_with_secrets")
    def test_proxy_restart(self, mock_get_env: Mock, mock_subprocess: Mock) -> None:
        """Test proxy restart command."""
        mock_get_env.return_value = {"SECRET": "value"}
        mock_subprocess.return_value = Mock(returncode=0)

        result = self.runner.invoke(proxy, ["restart"])

        self.assertEqual(result.exit_code, 0)
        cmd = mock_subprocess.call_args[0][0]
        self.assertIn("restart", cmd)

    @patch("commands.proxy.subprocess.run")
    @patch("commands.proxy.get_env_with_secrets")
    def test_proxy_logs(self, mock_get_env: Mock, mock_subprocess: Mock) -> None:
        """Test proxy logs command."""
        mock_get_env.return_value = {"SECRET": "value"}
        mock_subprocess.return_value = Mock(returncode=0)

        result = self.runner.invoke(proxy, ["logs"])

        self.assertEqual(result.exit_code, 0)
        cmd = mock_subprocess.call_args[0][0]
        self.assertIn("logs", cmd)
        self.assertIn("-f", cmd)


if __name__ == "__main__":
    unittest.main()
