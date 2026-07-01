#!/usr/bin/env python3

import os
import sys
import tempfile
import unittest
from unittest import mock
from unittest.mock import Mock, call

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bin.write_artifacts import inject_traefik_labels, write_upstream, write_upstreams
from lib.data import edge_network_name
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

    @mock.patch("bin.write_artifacts.build_reverse_egress_graph")
    @mock.patch("bin.write_artifacts.list_projects")
    @mock.patch("bin.write_artifacts.write_upstream")
    def test_write_upstreams_success(
        self, mock_write_upstream: Mock, mock_list_projects: Mock, mock_build_graph: Mock
    ) -> None:
        """Test writing all upstream configs successfully; each project receives the reverse graph."""
        mock_list_projects.return_value = ["project1", "project2"]
        mock_build_graph.return_value = {}

        result = write_upstreams()

        self.assertTrue(result)
        self.assertEqual(mock_write_upstream.call_count, 2)
        mock_write_upstream.assert_has_calls([call("project1", {}), call("project2", {})])

    @mock.patch("bin.write_artifacts.build_reverse_egress_graph")
    @mock.patch("bin.write_artifacts.list_projects")
    @mock.patch("bin.write_artifacts.write_upstream")
    def test_write_upstreams_failure(
        self, mock_write_upstream: Mock, mock_list_projects: Mock, mock_build_graph: Mock
    ) -> None:
        """Test writing upstream configs with failures."""
        mock_list_projects.return_value = ["project1", "project2"]
        mock_build_graph.return_value = {}
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
        import yaml

        compose_file = root() / "upstream" / "test-project" / "docker-compose.yml"
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
        """Consumer gets a per-edge network, not the provider's shared _default network."""
        compose = {
            "services": {
                "app": {"image": "app"},
            }
        }
        traefik = TraefikConfig(enabled=True, ingress=[], egress=["target-project:redis"])
        mock_load_project.return_value = (compose, traefik)

        write_upstream("test-project", {})

        import yaml

        compose_file = root() / "upstream" / "test-project" / "docker-compose.yml"
        with open(compose_file, encoding="utf-8") as f:
            result = yaml.safe_load(f)

        edge_net = edge_network_name("test-project", "target-project", "redis")
        # Consumer gets the per-edge network, declared external
        self.assertIn(edge_net, result["services"]["app"]["networks"])
        self.assertIn(edge_net, result["networks"])
        self.assertEqual(result["networks"][edge_net], {"external": True})
        # The provider's shared default network is NOT joined
        self.assertNotIn("target-project_default", result.get("networks", {}))

    @mock.patch("bin.write_artifacts.load_project")
    def test_write_upstream_network_assignment_with_both(self, mock_load_project: Mock) -> None:
        """Services with both ingress and egress get proxynet and the per-edge network."""
        compose = {
            "services": {
                "api": {"image": "api"},
            }
        }
        ingress = Ingress(service="api", domain="api.example.com", port=8080, router="http")
        traefik = TraefikConfig(enabled=True, ingress=[ingress], egress=["db-project:postgres"])
        mock_load_project.return_value = (compose, traefik)

        write_upstream("test-project", {})

        import yaml

        compose_file = root() / "upstream" / "test-project" / "docker-compose.yml"
        with open(compose_file, encoding="utf-8") as f:
            result = yaml.safe_load(f)

        edge_net = edge_network_name("test-project", "db-project", "postgres")
        # Service gets both proxynet (for Traefik) and the per-edge network (for egress)
        self.assertIn("proxynet", result["services"]["api"]["networks"])
        self.assertIn(edge_net, result["services"]["api"]["networks"])
        # The provider's shared default network is NOT joined
        self.assertNotIn("db-project_default", result.get("networks", {}))

    @mock.patch("bin.write_artifacts.load_project")
    def test_write_upstream_ipv4_address_mapping_form(self, mock_load_project: Mock) -> None:
        """A static ipv4_address renders the networks block in mapping form on proxynet."""
        import yaml

        compose = {"services": {"web": {"image": "nginx"}}}
        ingress = Ingress(service="web", domain="example.com", port=80, router="http", ipv4_address="172.20.0.50")
        traefik = TraefikConfig(enabled=True, ingress=[ingress], egress=[])
        mock_load_project.return_value = (compose, traefik)

        write_upstream("test-project")

        with open(root() / "upstream" / "test-project" / "docker-compose.yml", encoding="utf-8") as f:
            result = yaml.safe_load(f)

        networks = result["services"]["web"]["networks"]
        self.assertIsInstance(networks, dict)
        self.assertEqual(networks["proxynet"], {"ipv4_address": "172.20.0.50"})

    @mock.patch("bin.write_artifacts.load_project")
    def test_write_upstream_dns_override(self, mock_load_project: Mock) -> None:
        """An explicit dns list on ingress replaces the honeypot injection verbatim."""
        import yaml

        compose = {"services": {"web": {"image": "nginx"}}}
        ingress = Ingress(service="web", domain="example.com", port=80, router="http", dns=["127.0.0.11", "1.1.1.1"])
        traefik = TraefikConfig(enabled=True, ingress=[ingress], egress=[])
        mock_load_project.return_value = (compose, traefik)

        write_upstream("test-project")

        with open(root() / "upstream" / "test-project" / "docker-compose.yml", encoding="utf-8") as f:
            result = yaml.safe_load(f)

        self.assertEqual(result["services"]["web"]["dns"], ["127.0.0.11", "1.1.1.1"])

    @mock.patch("bin.write_artifacts.load_project")
    def test_write_upstream_no_ipv4_keeps_list_form(self, mock_load_project: Mock) -> None:
        """Without a static IP the networks block stays in list form (no churn)."""
        import yaml

        compose = {"services": {"web": {"image": "nginx"}}}
        ingress = Ingress(service="web", domain="example.com", port=80, router="http")
        traefik = TraefikConfig(enabled=True, ingress=[ingress], egress=[])
        mock_load_project.return_value = (compose, traefik)

        write_upstream("test-project")

        with open(root() / "upstream" / "test-project" / "docker-compose.yml", encoding="utf-8") as f:
            result = yaml.safe_load(f)

        self.assertIsInstance(result["services"]["web"]["networks"], list)
        self.assertIn("proxynet", result["services"]["web"]["networks"])

    @mock.patch("bin.write_artifacts.load_project")
    def test_write_upstream_provider_creates_edge_network(self, mock_load_project: Mock) -> None:
        """Provider creates named edge networks and attaches only the declared service."""
        import yaml

        compose = {
            "services": {
                "redis": {"image": "redis"},
                "postgres": {"image": "postgres"},
            }
        }
        traefik = TraefikConfig(enabled=True, ingress=[], egress=[])
        mock_load_project.return_value = (compose, traefik)

        # Consumer-a declared egress to this provider's redis service
        reverse_graph = {"provider": [("consumer-a", "redis")]}
        write_upstream("provider", reverse_graph)

        with open(root() / "upstream" / "provider" / "docker-compose.yml", encoding="utf-8") as f:
            result = yaml.safe_load(f)

        edge_net = edge_network_name("consumer-a", "provider", "redis")
        # Provider declares the network with an explicit Docker name (not external)
        self.assertIn(edge_net, result["networks"])
        self.assertEqual(result["networks"][edge_net], {"name": edge_net})
        # Only the declared service is attached to the edge network
        self.assertIn(edge_net, result["services"]["redis"]["networks"])
        self.assertNotIn(edge_net, result["services"]["postgres"]["networks"])

    @mock.patch("bin.write_artifacts.load_project")
    def test_write_upstream_co_consumer_isolation(self, mock_load_project: Mock) -> None:
        """Two consumers egressing to the same service get separate, disjoint edge networks."""
        import yaml

        compose = {"services": {"redis": {"image": "redis"}}}
        traefik = TraefikConfig(enabled=True, ingress=[], egress=[])
        mock_load_project.return_value = (compose, traefik)

        reverse_graph = {"provider": [("consumer-a", "redis"), ("consumer-b", "redis")]}
        write_upstream("provider", reverse_graph)

        with open(root() / "upstream" / "provider" / "docker-compose.yml", encoding="utf-8") as f:
            result = yaml.safe_load(f)

        edge_a = edge_network_name("consumer-a", "provider", "redis")
        edge_b = edge_network_name("consumer-b", "provider", "redis")
        # Both edge networks are distinct
        self.assertNotEqual(edge_a, edge_b)
        # Both are declared on the provider
        self.assertIn(edge_a, result["networks"])
        self.assertIn(edge_b, result["networks"])
        # Both consumers' networks are explicitly named (not external — provider creates them)
        self.assertEqual(result["networks"][edge_a], {"name": edge_a})
        self.assertEqual(result["networks"][edge_b], {"name": edge_b})

    @mock.patch("bin.write_artifacts.load_project")
    def test_write_upstream_least_privilege_provider(self, mock_load_project: Mock) -> None:
        """Consumer's edge network only attaches the named service — not other provider services."""
        import yaml

        compose = {
            "services": {
                "redis": {"image": "redis"},
                "other-svc": {"image": "other"},
            }
        }
        traefik = TraefikConfig(enabled=True, ingress=[], egress=[])
        mock_load_project.return_value = (compose, traefik)

        reverse_graph = {"provider": [("consumer-a", "redis")]}
        write_upstream("provider", reverse_graph)

        with open(root() / "upstream" / "provider" / "docker-compose.yml", encoding="utf-8") as f:
            result = yaml.safe_load(f)

        edge_net = edge_network_name("consumer-a", "provider", "redis")
        # redis is on the edge network — consumer can reach it
        self.assertIn(edge_net, result["services"]["redis"]["networks"])
        # other-svc is NOT on the edge network — consumer cannot reach it
        self.assertNotIn(edge_net, result["services"]["other-svc"]["networks"])

    @mock.patch("bin.write_artifacts.load_project")
    def test_write_upstream_provider_service_preserves_default_network(self, mock_load_project: Mock) -> None:
        """Provider service attached to an edge network also retains the implicit default network."""
        import yaml

        compose = {
            "services": {
                "redis": {"image": "redis"},
                "postgres": {"image": "postgres"},
            }
        }
        traefik = TraefikConfig(enabled=True, ingress=[], egress=[])
        mock_load_project.return_value = (compose, traefik)

        reverse_graph = {"provider": [("consumer-a", "redis")]}
        write_upstream("provider", reverse_graph)

        with open(root() / "upstream" / "provider" / "docker-compose.yml", encoding="utf-8") as f:
            result = yaml.safe_load(f)

        edge_net = edge_network_name("consumer-a", "provider", "redis")
        # redis gets the edge net AND the default net (sibling reachability preserved)
        self.assertIn(edge_net, result["services"]["redis"]["networks"])
        self.assertIn("default", result["services"]["redis"]["networks"])
        # postgres is unaffected — no edge net, no forced default
        self.assertNotIn(edge_net, result["services"]["postgres"]["networks"])

    @mock.patch("bin.write_artifacts.load_project")
    def test_write_upstream_consumer_not_on_provider_default(self, mock_load_project: Mock) -> None:
        """Consumer joins edge network only; the provider's _default network is never added."""
        import yaml

        compose = {"services": {"app": {"image": "app"}}}
        traefik = TraefikConfig(enabled=True, ingress=[], egress=["db:postgres", "db:redis"])
        mock_load_project.return_value = (compose, traefik)

        write_upstream("consumer", {})

        with open(root() / "upstream" / "consumer" / "docker-compose.yml", encoding="utf-8") as f:
            result = yaml.safe_load(f)

        edge_postgres = edge_network_name("consumer", "db", "postgres")
        edge_redis = edge_network_name("consumer", "db", "redis")
        # Consumer gets separate edge nets per service
        self.assertIn(edge_postgres, result["services"]["app"]["networks"])
        self.assertIn(edge_redis, result["services"]["app"]["networks"])
        # Provider's shared default network is never joined
        self.assertNotIn("db_default", result.get("networks", {}))


if __name__ == "__main__":
    unittest.main()
