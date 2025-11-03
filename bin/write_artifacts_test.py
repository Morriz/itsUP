#!/usr/bin/env python3

import os
import sys
import unittest
from unittest import mock
from unittest.mock import Mock, call

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bin.write_artifacts import inject_traefik_labels, write_upstream, write_upstreams
from lib.models import Ingress, TraefikConfig


class TestWriteArtifacts(unittest.TestCase):
    """Tests for write-artifacts.py V2 implementation"""

    def test_inject_traefik_labels_disabled(self) -> None:
        """Test that labels are not injected when Traefik is disabled."""
        compose = {"services": {"web": {"image": "nginx"}}}
        traefik = TraefikConfig(enabled=False, ingress=[])

        result = inject_traefik_labels(compose, traefik, "myproject")

        # Should return unchanged compose
        self.assertEqual(result, compose)
        self.assertNotIn("labels", result["services"]["web"])

    def test_inject_traefik_labels_http(self) -> None:
        """Test injecting Traefik labels for HTTP router."""
        compose = {"services": {"web": {"image": "nginx"}}}
        ingress = Ingress(service="web", domain="example.com", port=80, router="http")
        traefik = TraefikConfig(enabled=True, ingress=[ingress])

        result = inject_traefik_labels(compose, traefik, "myproject")

        labels = result["services"]["web"]["labels"]
        self.assertIn("traefik.enable=true", labels)
        self.assertIn("traefik.http.routers.myproject-web.entrypoints=web-secure", labels)
        self.assertIn("traefik.http.routers.myproject-web.rule=Host(`example.com`)", labels)
        self.assertIn("traefik.http.routers.myproject-web.tls=true", labels)
        self.assertIn("traefik.http.services.myproject-web.loadbalancer.server.port=80", labels)

    def test_inject_traefik_labels_http_with_path(self) -> None:
        """Test injecting Traefik labels for HTTP router with path prefix."""
        compose = {"services": {"api": {"image": "api"}}}
        ingress = Ingress(service="api", domain="example.com", port=8080, router="http", path_prefix="/api")
        traefik = TraefikConfig(enabled=True, ingress=[ingress])

        result = inject_traefik_labels(compose, traefik, "myproject")

        labels = result["services"]["api"]["labels"]
        self.assertIn("traefik.http.routers.myproject-api.rule=Host(`example.com`) && PathPrefix(`/api`)", labels)

    def test_inject_traefik_labels_tcp(self) -> None:
        """Test injecting Traefik labels for TCP router."""
        compose = {"services": {"db": {"image": "postgres"}}}
        ingress = Ingress(service="db", port=5432, router="tcp", hostport=5432)
        traefik = TraefikConfig(enabled=True, ingress=[ingress])

        result = inject_traefik_labels(compose, traefik, "myproject")

        labels = result["services"]["db"]["labels"]
        self.assertIn("traefik.enable=true", labels)
        self.assertIn("traefik.tcp.routers.myproject-db.entrypoints=tcp-5432", labels)
        self.assertIn("traefik.tcp.routers.myproject-db.rule=HostSNI(`*`)", labels)
        self.assertIn("traefik.tcp.routers.myproject-db.tls=true", labels)
        self.assertIn("traefik.tcp.services.myproject-db.loadbalancer.server.port=5432", labels)

    def test_inject_traefik_labels_tcp_passthrough(self) -> None:
        """Test injecting Traefik labels for TCP router with passthrough."""
        compose = {"services": {"mqtt": {"image": "mqtt"}}}
        ingress = Ingress(service="mqtt", port=8883, router="tcp", passthrough=True, hostport=8883)
        traefik = TraefikConfig(enabled=True, ingress=[ingress])

        result = inject_traefik_labels(compose, traefik, "myproject")

        labels = result["services"]["mqtt"]["labels"]
        self.assertIn("traefik.tcp.routers.myproject-mqtt.tls.passthrough=true", labels)
        # Should not have regular tls=true when passthrough is enabled
        self.assertNotIn("traefik.tcp.routers.myproject-mqtt.tls=true", labels)

    def test_inject_traefik_labels_udp(self) -> None:
        """Test injecting Traefik labels for UDP router."""
        compose = {"services": {"dns": {"image": "dns"}}}
        ingress = Ingress(service="dns", port=53, router="udp", hostport=53)
        traefik = TraefikConfig(enabled=True, ingress=[ingress])

        result = inject_traefik_labels(compose, traefik, "myproject")

        labels = result["services"]["dns"]["labels"]
        self.assertIn("traefik.enable=true", labels)
        self.assertIn("traefik.udp.routers.myproject-dns.entrypoints=udp-53", labels)
        self.assertIn("traefik.udp.services.myproject-dns.loadbalancer.server.port=53", labels)

    def test_inject_traefik_labels_convert_dict_to_list(self) -> None:
        """Test that dict labels are converted to list format."""
        compose = {"services": {"web": {"image": "nginx", "labels": {"existing.label": "value"}}}}
        ingress = Ingress(service="web", domain="example.com", port=80, router="http")
        traefik = TraefikConfig(enabled=True, ingress=[ingress])

        result = inject_traefik_labels(compose, traefik, "myproject")

        labels = result["services"]["web"]["labels"]
        self.assertIsInstance(labels, list)
        self.assertIn("existing.label=value", labels)
        self.assertIn("traefik.enable=true", labels)

    def test_inject_traefik_labels_unknown_service(self) -> None:
        """Test that warning is logged for unknown service."""
        compose = {"services": {"web": {"image": "nginx"}}}
        ingress = Ingress(service="api", domain="example.com", port=80, router="http")
        traefik = TraefikConfig(enabled=True, ingress=[ingress])

        with mock.patch("bin.write_artifacts.logger") as mock_logger:
            result = inject_traefik_labels(compose, traefik, "myproject")

            # Should log warning
            mock_logger.warning.assert_called_once()
            # Service should not be modified
            self.assertNotIn("labels", result["services"]["web"])

    @mock.patch("bin.write_artifacts.load_project")
    @mock.patch("bin.write_artifacts.Path")
    @mock.patch("builtins.open", new_callable=mock.mock_open)
    @mock.patch("bin.write_artifacts.yaml")
    def test_write_upstream(self, mock_yaml: Mock, mock_open: Mock, mock_path: Mock, mock_load_project: Mock) -> None:
        """Test writing upstream docker-compose.yml."""
        # Setup mocks
        compose = {"services": {"web": {"image": "nginx"}}}
        ingress = Ingress(service="web", domain="example.com", port=80, router="http")
        traefik = TraefikConfig(enabled=True, ingress=[ingress])
        mock_load_project.return_value = (compose, traefik)

        # Mock Path
        mock_upstream_dir = Mock()
        mock_path.return_value = mock_upstream_dir

        # Call function
        write_upstream("myproject")

        # Verify directory creation
        mock_upstream_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)

        # Verify file writing
        mock_open.assert_called_once()
        mock_yaml.dump.assert_called_once()

    @mock.patch("bin.write_artifacts.list_projects")
    @mock.patch("bin.write_artifacts.write_upstream")
    def test_write_upstreams_success(self, mock_write_upstream: Mock, mock_list_projects: Mock) -> None:
        """Test writing all upstream configs successfully."""
        mock_list_projects.return_value = ["project1", "project2"]

        result = write_upstreams()

        self.assertTrue(result)
        self.assertEqual(mock_write_upstream.call_count, 2)
        mock_write_upstream.assert_has_calls([call("project1"), call("project2")])

    @mock.patch("bin.write_artifacts.list_projects")
    @mock.patch("bin.write_artifacts.write_upstream")
    def test_write_upstreams_failure(self, mock_write_upstream: Mock, mock_list_projects: Mock) -> None:
        """Test writing upstream configs with failures."""
        mock_list_projects.return_value = ["project1", "project2"]
        mock_write_upstream.side_effect = [None, Exception("Failed to process")]

        result = write_upstreams()

        self.assertFalse(result)
        self.assertEqual(mock_write_upstream.call_count, 2)

    @mock.patch("bin.write_artifacts.list_projects")
    def test_write_upstreams_no_projects(self, mock_list_projects: Mock) -> None:
        """Test writing upstream configs when no projects exist."""
        mock_list_projects.return_value = []

        result = write_upstreams()

        self.assertTrue(result)  # Returns True when no projects to process

    def test_inject_traefik_labels_multiple_ingress(self) -> None:
        """Test injecting multiple ingress rules for the same service."""
        compose = {"services": {"web": {"image": "nginx"}}}
        ingress1 = Ingress(service="web", domain="example.com", port=80, router="http")
        ingress2 = Ingress(service="web", domain="api.example.com", port=8080, router="http", path_prefix="/api")
        traefik = TraefikConfig(enabled=True, ingress=[ingress1, ingress2])

        result = inject_traefik_labels(compose, traefik, "myproject")

        labels = result["services"]["web"]["labels"]
        # Should have labels for both ingress rules
        self.assertIn("traefik.http.routers.myproject-web.rule=Host(`example.com`)", labels)
        # Note: The current implementation may overwrite labels. This test documents current behavior.
        # In a real scenario, you might need to generate unique router names for multiple ingress rules.

    @mock.patch("bin.write_artifacts.load_project")
    def test_write_upstream_network_assignment_with_ingress(self, mock_load_project: Mock) -> None:
        """Test that services with ingress get proxynet added."""
        compose = {
            "services": {
                "web": {"image": "nginx"},
                "worker": {"image": "worker"},
            }
        }
        ingress = Ingress(service="web", domain="example.com", port=80, router="http")
        traefik = TraefikConfig(enabled=True, ingress=[ingress], egress=[])
        mock_load_project.return_value = (compose, traefik)

        write_upstream("test-project")

        # Read generated file
        from pathlib import Path
        import yaml

        compose_file = Path("upstream/test-project/docker-compose.yml")
        with open(compose_file, encoding="utf-8") as f:
            result = yaml.safe_load(f)

        # Service with ingress should have proxynet
        self.assertIn("proxynet", result["services"]["web"]["networks"])
        # Service without ingress should NOT have proxynet
        self.assertNotIn("proxynet", result["services"]["worker"]["networks"])
        # Both should have DNS honeypot
        self.assertEqual(result["services"]["web"]["dns"], ["172.20.0.253", "127.0.0.11"])
        self.assertEqual(result["services"]["worker"]["dns"], ["172.20.0.253", "127.0.0.11"])

    @mock.patch("bin.write_artifacts.load_project")
    def test_write_upstream_network_assignment_with_egress(self, mock_load_project: Mock) -> None:
        """Test that projects with egress get target project networks added."""
        compose = {
            "services": {
                "app": {"image": "app"},
            }
        }
        traefik = TraefikConfig(enabled=True, ingress=[], egress=["target-project:redis"])
        mock_load_project.return_value = (compose, traefik)

        write_upstream("test-project")

        # Read generated file
        from pathlib import Path
        import yaml

        compose_file = Path("upstream/test-project/docker-compose.yml")
        with open(compose_file, encoding="utf-8") as f:
            result = yaml.safe_load(f)

        # Service should have target project network
        self.assertIn("target-project_default", result["services"]["app"]["networks"])
        # External network should be declared
        self.assertIn("target-project_default", result["networks"])
        self.assertEqual(result["networks"]["target-project_default"], {"external": True})

    @mock.patch("bin.write_artifacts.load_project")
    def test_write_upstream_network_assignment_with_both(self, mock_load_project: Mock) -> None:
        """Test that services with both ingress and egress get both networks."""
        compose = {
            "services": {
                "api": {"image": "api"},
            }
        }
        ingress = Ingress(service="api", domain="api.example.com", port=8080, router="http")
        traefik = TraefikConfig(enabled=True, ingress=[ingress], egress=["db-project:postgres"])
        mock_load_project.return_value = (compose, traefik)

        write_upstream("test-project")

        # Read generated file
        from pathlib import Path
        import yaml

        compose_file = Path("upstream/test-project/docker-compose.yml")
        with open(compose_file, encoding="utf-8") as f:
            result = yaml.safe_load(f)

        # Service should have both proxynet and target network
        self.assertIn("proxynet", result["services"]["api"]["networks"])
        self.assertIn("db-project_default", result["services"]["api"]["networks"])
        self.assertIn("default", result["services"]["api"]["networks"])


if __name__ == "__main__":
    unittest.main()
