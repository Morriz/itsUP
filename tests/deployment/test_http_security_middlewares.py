from pathlib import Path
from typing import cast

import pytest

from tests.deployment.conftest import (
    ConfigMap,
    entrypoint,
    entrypoint_middlewares,
    generate,
    write_project_tree,
)

SPEC_ID = "project/spec/feature/deployment/http-security-middlewares"
DEFAULT_HEADERS_MIDDLEWARE = "default-headers@file"
RATE_LIMIT_MIDDLEWARE = "rate-limit@file"
DEFAULT_HEADERS_KEY = "default-headers"
RATE_LIMIT_KEY = "rate-limit"


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-HSM1")
def test_default_security_middlewares_attached_at_web_secure(isolated_itsup_root: Path) -> None:
    write_project_tree(isolated_itsup_root)

    traefik_config, middlewares_config = generate(isolated_itsup_root)

    web_secure_middlewares = entrypoint_middlewares(entrypoint(traefik_config, "web-secure"))
    assert web_secure_middlewares.index(DEFAULT_HEADERS_MIDDLEWARE) < web_secure_middlewares.index(
        RATE_LIMIT_MIDDLEWARE
    )

    web_middlewares = entrypoint_middlewares(entrypoint(traefik_config, "web"))
    assert DEFAULT_HEADERS_MIDDLEWARE not in web_middlewares
    assert RATE_LIMIT_MIDDLEWARE not in web_middlewares

    dynamic_middlewares = cast(ConfigMap, middlewares_config["http"])
    dynamic_middlewares = cast(ConfigMap, dynamic_middlewares["middlewares"])
    assert DEFAULT_HEADERS_KEY in dynamic_middlewares
    assert RATE_LIMIT_KEY in dynamic_middlewares
