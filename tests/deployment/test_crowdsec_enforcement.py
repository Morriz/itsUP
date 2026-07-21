from pathlib import Path
from typing import cast

import pytest

from tests.deployment.conftest import (
    ROUTER_IP,
    ConfigMap,
    entrypoint,
    entrypoint_middlewares,
    generate,
    write_project_tree,
)

SPEC_ID = "project/spec/feature/deployment/crowdsec-enforcement"
ROUTER_IP_CIDR = f"{ROUTER_IP}/32"
PRIVATE_RANGES = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
CROWDSEC_MIDDLEWARE = "crowdsec@file"


def _bouncer_options(middlewares_config: ConfigMap) -> ConfigMap:
    http_config = cast(ConfigMap, middlewares_config["http"])
    middlewares = cast(ConfigMap, http_config["middlewares"])
    crowdsec = cast(ConfigMap, middlewares["crowdsec"])
    plugin = cast(ConfigMap, crowdsec["plugin"])
    return cast(ConfigMap, plugin["bouncer"])


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-CSE1")
def test_bouncer_attached_at_http_entrypoints_when_enabled(isolated_itsup_root: Path) -> None:
    write_project_tree(isolated_itsup_root, crowdsec_enabled=True)

    traefik_config, middlewares_config = generate(isolated_itsup_root)

    web_middlewares = entrypoint_middlewares(entrypoint(traefik_config, "web"))
    web_secure_middlewares = entrypoint_middlewares(entrypoint(traefik_config, "web-secure"))

    assert CROWDSEC_MIDDLEWARE in web_middlewares
    assert CROWDSEC_MIDDLEWARE in web_secure_middlewares

    client_trusted_ips = cast(list[object], _bouncer_options(middlewares_config)["clientTrustedIPs"])

    assert ROUTER_IP_CIDR in client_trusted_ips
    for cidr in PRIVATE_RANGES:
        assert cidr in client_trusted_ips


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-CSE1")
def test_no_bouncer_middleware_when_disabled(isolated_itsup_root: Path) -> None:
    write_project_tree(isolated_itsup_root, crowdsec_enabled=False)

    traefik_config, _ = generate(isolated_itsup_root)

    web_middlewares = entrypoint_middlewares(entrypoint(traefik_config, "web"))
    web_secure_middlewares = entrypoint_middlewares(entrypoint(traefik_config, "web-secure"))

    assert CROWDSEC_MIDDLEWARE not in web_middlewares
    assert CROWDSEC_MIDDLEWARE not in web_secure_middlewares
