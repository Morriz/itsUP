#!/usr/bin/env python3

import os
import sys
import unittest
from typing import Any, Dict, List
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.models import TraefikConfig


class TestDeployUpstreamProject(unittest.TestCase):
    """Tests for deploy_upstream_project() egress edge-network gate."""

    def _make_compose(self) -> Dict[str, Any]:
        return {"services": {"app": {"image": "app"}}}

    @patch("lib.deploy.subprocess.run")
    @patch("lib.deploy.write_upstream")
    @patch("lib.deploy.load_project")
    def test_no_egress_skips_network_check(
        self, mock_load_project: Mock, mock_write_upstream: Mock, mock_run: Mock
    ) -> None:
        """Project with no egress declarations deploys without any docker-inspect calls."""
        from lib.deploy import deploy_upstream_project

        traefik = TraefikConfig(enabled=True, ingress=[], egress=[])
        mock_load_project.return_value = (self._make_compose(), traefik)
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        deploy_upstream_project("consumer")

        inspect_calls = [c for c in mock_run.call_args_list if len(c.args[0]) >= 3 and c.args[0][1] == "network"]
        self.assertEqual(inspect_calls, [])

    @patch("lib.deploy.subprocess.run")
    @patch("lib.deploy.write_upstream")
    @patch("lib.deploy.load_project")
    def test_existing_edge_network_deploys_normally(
        self, mock_load_project: Mock, mock_write_upstream: Mock, mock_run: Mock
    ) -> None:
        """When the edge network exists, deploy proceeds without error."""
        from lib.deploy import deploy_upstream_project

        traefik = TraefikConfig(enabled=True, ingress=[], egress=["db:redis"])
        mock_load_project.return_value = (self._make_compose(), traefik)
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        # Should not raise
        deploy_upstream_project("consumer")

    @patch("lib.deploy.subprocess.run")
    @patch("lib.deploy.write_upstream")
    @patch("lib.deploy.load_project")
    def test_missing_edge_network_raises_runtime_error(
        self, mock_load_project: Mock, mock_write_upstream: Mock, mock_run: Mock
    ) -> None:
        """Missing edge network raises RuntimeError with actionable guidance."""
        from lib.deploy import deploy_upstream_project

        traefik = TraefikConfig(enabled=True, ingress=[], egress=["db:redis"])
        mock_load_project.return_value = (self._make_compose(), traefik)

        def run_side_effect(cmd: List[str], **kwargs: Any) -> Mock:
            if len(cmd) >= 3 and cmd[1] == "network" and cmd[2] == "inspect":
                return Mock(returncode=1, stdout="", stderr="Error: No such network")
            return Mock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = run_side_effect

        with self.assertRaises(RuntimeError) as ctx:
            deploy_upstream_project("consumer")

        self.assertIn("itsup apply db", str(ctx.exception))

    @patch("lib.deploy.subprocess.run")
    @patch("lib.deploy.write_upstream")
    @patch("lib.deploy.load_project")
    def test_multiple_egress_all_must_exist(
        self, mock_load_project: Mock, mock_write_upstream: Mock, mock_run: Mock
    ) -> None:
        """All declared egress edge networks must exist; first missing one raises."""
        from lib.deploy import deploy_upstream_project

        traefik = TraefikConfig(enabled=True, ingress=[], egress=["db:redis", "cache:memcached"])
        mock_load_project.return_value = (self._make_compose(), traefik)

        call_count = [0]

        def run_side_effect(cmd: List[str], **kwargs: Any) -> Mock:
            if len(cmd) >= 3 and cmd[1] == "network" and cmd[2] == "inspect":
                call_count[0] += 1
                if call_count[0] == 2:
                    return Mock(returncode=1, stdout="", stderr="Error: No such network")
            return Mock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = run_side_effect

        with self.assertRaises(RuntimeError) as ctx:
            deploy_upstream_project("consumer")

        self.assertIn("itsup apply cache", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
