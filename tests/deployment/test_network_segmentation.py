from collections.abc import Mapping
from pathlib import Path
from typing import cast
from unittest import mock
from unittest.mock import Mock

import pytest
import yaml

from bin.write_artifacts import DNS_HONEYPOT, write_upstream
from lib.data import edge_network_name
from lib.models import Ingress, TraefikConfig
from lib.paths import root

SPEC_ID = "project/spec/feature/deployment/network-segmentation"
PROXYNET = "proxynet"
DEFAULT_NETWORK = "default"
ComposeMap = Mapping[str, object]
ServiceMap = Mapping[str, object]


def _generate_upstream(
    project_name: str,
    compose: ComposeMap,
    traefik: TraefikConfig,
    reverse_graph: dict[str, list[tuple[str, str]]] | None = None,
) -> ComposeMap:
    with mock.patch("bin.write_artifacts.load_project") as mock_load_project:
        mocked_load_project: Mock = mock_load_project
        mocked_load_project.return_value = (compose, traefik)
        write_upstream(project_name, reverse_graph)

    compose_file = root() / "upstream" / project_name / "docker-compose.yml"
    with open(compose_file, encoding="utf-8") as file:
        return cast(ComposeMap, yaml.safe_load(file))


def _service(result: ComposeMap, name: str) -> ServiceMap:
    services = cast(Mapping[str, ServiceMap], result["services"])
    return services[name]


def _service_networks(result: ComposeMap, name: str) -> list[str]:
    return cast(list[str], _service(result, name)["networks"])


def _service_networks_map(result: ComposeMap, name: str) -> Mapping[str, object]:
    return cast(Mapping[str, object], _service(result, name)["networks"])


def _service_dns(result: ComposeMap, name: str) -> list[str]:
    return cast(list[str], _service(result, name)["dns"])


def _top_networks(result: ComposeMap) -> Mapping[str, object]:
    return cast(Mapping[str, object], result["networks"])


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-PROX1")
def test_ingress_service_joins_proxynet_and_plain_service_does_not(isolated_itsup_root: Path) -> None:
    """UC-PROX1: A service with an ingress row joins proxynet; one without does not."""
    compose: ComposeMap = {
        "services": {
            "web": {"image": "nginx"},
            "worker": {"image": "worker"},
        }
    }
    ingress = Ingress(service="web", domain="example.com", port=80, router="http")
    traefik = TraefikConfig(enabled=True, ingress=[ingress], egress=[])

    result = _generate_upstream("test-project", compose, traefik)

    assert PROXYNET in _service_networks(result, "web")
    assert PROXYNET not in _service_networks(result, "worker")


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-ISO1")
def test_service_without_ingress_or_egress_stays_project_local_only(isolated_itsup_root: Path) -> None:
    """UC-ISO1: A service with neither ingress nor egress stays project-local only."""
    compose: ComposeMap = {"services": {"app": {"image": "app"}}}
    traefik = TraefikConfig(enabled=True, ingress=[], egress=[])

    result = _generate_upstream("test-project", compose, traefik)

    networks = _service_networks(result, "app")
    assert PROXYNET not in networks
    assert _top_networks(result) == {PROXYNET: {"external": True}}


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-DNS1")
def test_every_service_receives_honeypot_and_docker_dns(isolated_itsup_root: Path) -> None:
    """UC-DNS1: Every service receives the DNS honeypot and Docker DNS."""
    compose: ComposeMap = {
        "services": {
            "web": {"image": "nginx"},
            "worker": {"image": "worker"},
        }
    }
    traefik = TraefikConfig(enabled=True, ingress=[], egress=[])

    result = _generate_upstream("test-project", compose, traefik)

    assert _service_dns(result, "web") == [DNS_HONEYPOT, "127.0.0.11"]
    assert _service_dns(result, "worker") == [DNS_HONEYPOT, "127.0.0.11"]


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-DNS2")
def test_ingress_dns_override_replaces_honeypot_injection(isolated_itsup_root: Path) -> None:
    """UC-DNS2: An explicit dns list on an ingress row replaces the honeypot injection."""
    explicit_dns = ["127.0.0.11", "1.1.1.1"]
    compose: ComposeMap = {"services": {"web": {"image": "nginx"}}}
    ingress = Ingress(service="web", domain="example.com", port=80, router="http", dns=explicit_dns)
    traefik = TraefikConfig(enabled=True, ingress=[ingress], egress=[])

    result = _generate_upstream("test-project", compose, traefik)

    assert _service_dns(result, "web") == explicit_dns
    assert DNS_HONEYPOT not in _service_dns(result, "web")


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-EGR1")
def test_consumer_egress_joins_edge_network_not_provider_default(isolated_itsup_root: Path) -> None:
    """UC-EGR1: A consumer's egress joins a per-edge network, never the provider's default."""
    compose: ComposeMap = {"services": {"app": {"image": "app"}}}
    traefik = TraefikConfig(enabled=True, ingress=[], egress=["target-project:redis"])

    result = _generate_upstream("test-project", compose, traefik, {})

    edge_net = edge_network_name("test-project", "target-project", "redis")
    assert edge_net in _service_networks(result, "app")
    assert _top_networks(result)[edge_net] == {"external": True}
    assert "target-project_default" not in _top_networks(result)


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-EGR2")
def test_multiple_egress_entries_create_distinct_service_edges(isolated_itsup_root: Path) -> None:
    """UC-EGR2: Multiple egress entries produce separate per-service edge networks."""
    compose: ComposeMap = {"services": {"app": {"image": "app"}}}
    traefik = TraefikConfig(enabled=True, ingress=[], egress=["db:postgres", "db:redis"])

    result = _generate_upstream("consumer", compose, traefik, {})

    edge_postgres = edge_network_name("consumer", "db", "postgres")
    edge_redis = edge_network_name("consumer", "db", "redis")
    assert edge_postgres in _service_networks(result, "app")
    assert edge_redis in _service_networks(result, "app")
    assert edge_postgres != edge_redis
    assert "db_default" not in _top_networks(result)


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-EGR3")
def test_service_with_ingress_and_egress_joins_proxynet_and_edge(isolated_itsup_root: Path) -> None:
    """UC-EGR3: A service with both ingress and egress joins proxynet and its edge network."""
    compose: ComposeMap = {"services": {"api": {"image": "api"}}}
    ingress = Ingress(service="api", domain="api.example.com", port=8080, router="http")
    traefik = TraefikConfig(enabled=True, ingress=[ingress], egress=["db-project:postgres"])

    result = _generate_upstream("test-project", compose, traefik, {})

    edge_net = edge_network_name("test-project", "db-project", "postgres")
    assert PROXYNET in _service_networks(result, "api")
    assert edge_net in _service_networks(result, "api")
    assert "db-project_default" not in _top_networks(result)


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-PROV1")
def test_provider_creates_named_edge_and_attaches_only_declared_service(isolated_itsup_root: Path) -> None:
    """UC-PROV1: The provider creates the named edge network and attaches only the declared service."""
    compose: ComposeMap = {
        "services": {
            "redis": {"image": "redis"},
            "postgres": {"image": "postgres"},
        }
    }
    traefik = TraefikConfig(enabled=True, ingress=[], egress=[])

    result = _generate_upstream("provider", compose, traefik, {"provider": [("consumer-a", "redis")]})

    edge_net = edge_network_name("consumer-a", "provider", "redis")
    assert _top_networks(result)[edge_net] == {"name": edge_net}
    assert edge_net in _service_networks(result, "redis")
    assert edge_net not in _service_networks(result, "postgres")


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-PROV2")
def test_provider_edge_service_retains_default_network(isolated_itsup_root: Path) -> None:
    """UC-PROV2: A provider service on an edge network retains its default network."""
    compose: ComposeMap = {
        "services": {
            "redis": {"image": "redis"},
            "postgres": {"image": "postgres"},
        }
    }
    traefik = TraefikConfig(enabled=True, ingress=[], egress=[])

    result = _generate_upstream("provider", compose, traefik, {"provider": [("consumer-a", "redis")]})

    edge_net = edge_network_name("consumer-a", "provider", "redis")
    assert edge_net in _service_networks(result, "redis")
    assert DEFAULT_NETWORK in _service_networks(result, "redis")
    assert edge_net not in _service_networks(result, "postgres")


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-PROV3")
def test_two_consumers_get_separate_provider_edge_networks(isolated_itsup_root: Path) -> None:
    """UC-PROV3: Two consumers of the same service get separate, disjoint edge networks."""
    compose: ComposeMap = {"services": {"redis": {"image": "redis"}}}
    traefik = TraefikConfig(enabled=True, ingress=[], egress=[])
    reverse_graph = {"provider": [("consumer-a", "redis"), ("consumer-b", "redis")]}

    result = _generate_upstream("provider", compose, traefik, reverse_graph)

    edge_a = edge_network_name("consumer-a", "provider", "redis")
    edge_b = edge_network_name("consumer-b", "provider", "redis")
    assert edge_a != edge_b
    assert _top_networks(result)[edge_a] == {"name": edge_a}
    assert _top_networks(result)[edge_b] == {"name": edge_b}


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-IP1")
def test_static_ip_renders_mapping_form_on_proxynet(isolated_itsup_root: Path) -> None:
    """UC-IP1: An ingress static IP renders the networks block in mapping form on proxynet."""
    compose: ComposeMap = {"services": {"web": {"image": "nginx"}}}
    ingress = Ingress(service="web", domain="example.com", port=80, router="http", ipv4_address="172.20.0.50")
    traefik = TraefikConfig(enabled=True, ingress=[ingress], egress=[])

    result = _generate_upstream("test-project", compose, traefik)

    networks = _service_networks_map(result, "web")
    assert isinstance(networks, dict)
    assert networks[PROXYNET] == {"ipv4_address": "172.20.0.50"}


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-IP2")
def test_without_static_ip_networks_block_stays_list_form(isolated_itsup_root: Path) -> None:
    """UC-IP2: Without a static IP the networks block stays in list form."""
    compose: ComposeMap = {"services": {"web": {"image": "nginx"}}}
    ingress = Ingress(service="web", domain="example.com", port=80, router="http")
    traefik = TraefikConfig(enabled=True, ingress=[ingress], egress=[])

    result = _generate_upstream("test-project", compose, traefik)

    networks = _service_networks(result, "web")
    assert isinstance(networks, list)
    assert PROXYNET in networks
