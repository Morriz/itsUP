#!/usr/bin/env python3

import os
import sys
import tempfile
import unittest
from unittest import mock
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bin.write_artifacts import inject_traefik_labels, write_upstream
from lib.models import Ingress, TraefikConfig
from lib.paths import root


class TestWriteArtifacts(unittest.TestCase):
    """Tests for write-artifacts.py V2 implementation"""

    def setUp(self) -> None:
        """Anchor each test's artifact tree under an isolated ITSUP_ROOT."""
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"ITSUP_ROOT": self._tmp.name})
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def test_inject_traefik_labels_disabled(self) -> None:
        """Test that labels are not injected when Traefik is disabled."""
        compose = {"services": {"web": {"image": "nginx"}}}
        traefik = TraefikConfig(enabled=False, ingress=[])

        result = inject_traefik_labels(compose, traefik, "myproject")

        # Should return unchanged compose
        self.assertEqual(result, compose)
        self.assertNotIn("labels", result["services"]["web"])

    def test_inject_traefik_labels_http(self) -> None:
        """HTTP router label injection uses port-qualified router names for uniqueness."""
        compose = {"services": {"web": {"image": "nginx"}}}
        ingress = Ingress(service="web", domain="example.com", port=80, router="http")
        traefik = TraefikConfig(enabled=True, ingress=[ingress])

        result = inject_traefik_labels(compose, traefik, "myproject")

        labels = result["services"]["web"]["labels"]
        self.assertIn("traefik.enable=true", labels)
        self.assertIn("traefik.http.routers.myproject-web-80.entrypoints=web-secure", labels)
        self.assertIn("traefik.http.routers.myproject-web-80.rule=Host(`example.com`)", labels)
        self.assertIn("traefik.http.routers.myproject-web-80.tls=true", labels)
        self.assertIn("traefik.http.services.myproject-web-80.loadbalancer.server.port=80", labels)

    def test_inject_traefik_labels_http_with_path(self) -> None:
        """HTTP router with path prefix uses port-qualified router name."""
        compose = {"services": {"api": {"image": "api"}}}
        ingress = Ingress(service="api", domain="example.com", port=8080, router="http", path_prefix="/api")
        traefik = TraefikConfig(enabled=True, ingress=[ingress])

        result = inject_traefik_labels(compose, traefik, "myproject")

        labels = result["services"]["api"]["labels"]
        self.assertIn("traefik.http.routers.myproject-api-8080.rule=Host(`example.com`) && PathPrefix(`/api`)", labels)

    def test_inject_traefik_labels_tcp(self) -> None:
        """TCP router: only traefik.enable=true injected; routing config lives in Traefik dynamic config."""
        compose = {"services": {"db": {"image": "postgres"}}}
        ingress = Ingress(service="db", port=5432, router="tcp", hostport=5432)
        traefik = TraefikConfig(enabled=True, ingress=[ingress])

        result = inject_traefik_labels(compose, traefik, "myproject")

        labels = result["services"]["db"]["labels"]
        self.assertIn("traefik.enable=true", labels)
        # TCP routing config lives in dynamic config files, not in compose labels
        self.assertFalse(any("traefik.tcp.routers" in lbl for lbl in labels))

    def test_inject_traefik_labels_tcp_passthrough(self) -> None:
        """TCP passthrough: only traefik.enable=true injected; routing config is in dynamic config."""
        compose = {"services": {"mqtt": {"image": "mqtt"}}}
        ingress = Ingress(service="mqtt", port=8883, router="tcp", passthrough=True, hostport=8883)
        traefik = TraefikConfig(enabled=True, ingress=[ingress])

        result = inject_traefik_labels(compose, traefik, "myproject")

        labels = result["services"]["mqtt"]["labels"]
        self.assertIn("traefik.enable=true", labels)
        self.assertFalse(any("traefik.tcp.routers" in lbl for lbl in labels))

    def test_inject_traefik_labels_udp(self) -> None:
        """UDP router: only traefik.enable=true injected; routing config lives in Traefik dynamic config."""
        compose = {"services": {"dns": {"image": "dns"}}}
        ingress = Ingress(service="dns", port=53, router="udp", hostport=53)
        traefik = TraefikConfig(enabled=True, ingress=[ingress])

        result = inject_traefik_labels(compose, traefik, "myproject")

        labels = result["services"]["dns"]["labels"]
        self.assertIn("traefik.enable=true", labels)
        self.assertFalse(any("traefik.udp.routers" in lbl for lbl in labels))

    def test_inject_traefik_labels_multiple_ingress(self) -> None:
        """Multiple ingress rules on one service get distinct port-qualified router names."""
        compose = {"services": {"web": {"image": "nginx"}}}
        ingress1 = Ingress(service="web", domain="example.com", port=80, router="http")
        ingress2 = Ingress(service="web", domain="api.example.com", port=8080, router="http", path_prefix="/api")
        traefik = TraefikConfig(enabled=True, ingress=[ingress1, ingress2])

        result = inject_traefik_labels(compose, traefik, "myproject")

        labels = result["services"]["web"]["labels"]
        self.assertIn("traefik.http.routers.myproject-web-80.rule=Host(`example.com`)", labels)
        self.assertIn(
            "traefik.http.routers.myproject-web-8080.rule=Host(`api.example.com`) && PathPrefix(`/api`)", labels
        )

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
    def test_write_upstream_generates_compose_file(self, mock_load_project: Mock) -> None:
        """write_upstream writes a docker-compose.yml to the upstream directory."""
        import yaml

        compose = {"services": {"web": {"image": "nginx"}}}
        ingress = Ingress(service="web", domain="example.com", port=80, router="http")
        traefik = TraefikConfig(enabled=True, ingress=[ingress], egress=[])
        mock_load_project.return_value = (compose, traefik)

        write_upstream("test-project")

        compose_file = root() / "upstream" / "test-project" / "docker-compose.yml"
        self.assertTrue(compose_file.exists())
        with open(compose_file, encoding="utf-8") as f:
            result = yaml.safe_load(f)
        self.assertIn("web", result["services"])


if __name__ == "__main__":
    unittest.main()
