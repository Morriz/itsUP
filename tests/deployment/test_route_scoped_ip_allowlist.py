from pathlib import Path
from typing import cast

import pytest
from syrupy.assertion import SnapshotAssertion

from lib.data import load_project
from tests.deployment.conftest import (
    ConfigMap,
    generate_dynamic_routers,
    write_external_host_project,
    write_project_tree,
)

SPEC_ID = "project/spec/feature/deployment/route-scoped-ip-allowlist"
ALLOW_SOURCE_IPS = ["192.168.1.1/32"]


def _external_routers(routers: ConfigMap, services: ConfigMap) -> dict[str, ConfigMap]:
    return {
        name: cast(ConfigMap, router)
        for name, router in routers.items()
        if cast(ConfigMap, router)["service"] in services
    }


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-RSIP3")
def test_external_host_config_rejects_malformed_allow_source_ips(
    isolated_itsup_root: Path, snapshot: SnapshotAssertion
) -> None:
    write_external_host_project(
        isolated_itsup_root,
        """
  - domain: api.example.com
    port: 8888
    router: http
    allow_source_ips: [not-an-ip]
""",
    )

    with pytest.raises(ValueError) as error:
        load_project("api-host")

    assert str(error.value) == snapshot


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-RSIP5")
def test_external_host_config_rejects_empty_allow_source_ips(
    isolated_itsup_root: Path, snapshot: SnapshotAssertion
) -> None:
    write_external_host_project(
        isolated_itsup_root,
        """
  - domain: api.example.com
    port: 8888
    router: http
    allow_source_ips: []
""",
    )

    with pytest.raises(ValueError) as error:
        load_project("api-host")

    assert str(error.value) == snapshot


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-RSIP1")
def test_external_host_routes_render_with_distinct_router_and_service_identities(isolated_itsup_root: Path) -> None:
    write_project_tree(isolated_itsup_root)
    write_external_host_project(
        isolated_itsup_root,
        """
  - domain: api.example.com
    path_prefix: /redirect
    port: 8888
    router: http
  - domain: api.example.com
    path_prefix: /file
    port: 8888
    router: http
    allow_source_ips:
      - 192.168.1.1/32
""",
    )

    config = generate_dynamic_routers(isolated_itsup_root)
    http_config = cast(ConfigMap, config["http"])
    routers = cast(ConfigMap, http_config["routers"])
    services = cast(ConfigMap, http_config["services"])
    api_routers = _external_routers(routers, services)

    assert len(api_routers) == 2
    assert {router["service"] for router in api_routers.values()} == set(api_routers)
    assert set(api_routers).issubset(services)


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-RSIP2")
def test_external_host_file_route_has_its_configured_ip_allowlist(isolated_itsup_root: Path) -> None:
    write_project_tree(isolated_itsup_root)
    write_external_host_project(
        isolated_itsup_root,
        """
  - domain: api.example.com
    path_prefix: /file
    port: 8888
    router: http
    allow_source_ips:
      - 192.168.1.1/32
""",
    )

    config = generate_dynamic_routers(isolated_itsup_root)
    http_config = cast(ConfigMap, config["http"])
    file_router = next(
        iter(
            _external_routers(
                cast(ConfigMap, http_config["routers"]), cast(ConfigMap, http_config["services"])
            ).values()
        )
    )
    middleware_name = cast(list[str], file_router["middlewares"])[0]
    middlewares = cast(ConfigMap, http_config["middlewares"])
    middleware = cast(ConfigMap, middlewares[middleware_name])

    assert cast(ConfigMap, middleware["ipAllowList"])["sourceRange"] == ALLOW_SOURCE_IPS


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-RSIP4")
def test_external_host_redirect_route_has_no_ip_allowlist(
    isolated_itsup_root: Path, snapshot: SnapshotAssertion
) -> None:
    write_project_tree(isolated_itsup_root)
    write_external_host_project(
        isolated_itsup_root,
        """
  - domain: api.example.com
    path_prefix: /redirect
    port: 8888
    router: http
""",
    )

    config = generate_dynamic_routers(isolated_itsup_root)
    http_config = cast(ConfigMap, config["http"])
    redirect_router = next(
        iter(
            _external_routers(
                cast(ConfigMap, http_config["routers"]), cast(ConfigMap, http_config["services"])
            ).values()
        )
    )

    assert redirect_router == snapshot
