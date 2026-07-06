#!/usr/bin/env python3

"""
Functional tests for artifact generation validation.

Validates that generated files are valid YAML and pass validation checks.
Uses REAL docker compose and traefik binaries.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from bin.write_artifacts import DNS_HONEYPOT, write_proxy_compose, write_upstream

# Path to real project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Expected-value literals asserted against generated artifacts.
SERVICES_KEY = "services"
WEB_SERVICE = "web"
DNS_KEY = "dns"
LABELS_KEY = "labels"
TRAEFIK_ENABLE = "traefik.enable=true"
RULE_MARKER = ".rule="
TEST_DOMAIN = "test.example.com"
NETWORKS_KEY = "networks"
PROXYNET = "proxynet"
ENTRYPOINTS_KEY = "entryPoints"
PROVIDERS_KEY = "providers"
LOG_KEY = "log"
LOG_LEVEL_DEBUG = "DEBUG"
API_KEY = "api"


# External-host HTTP route (the itsUP management API shape) asserted against output.
EXTERNAL_HOST_RULE = "Host(`api.example.com`)"
EXTERNAL_HOST_BACKEND = "http://127.0.0.1:8888/"

# Companion plain-HTTP redirect router identity markers.
REDIRECT_ENTRYPOINT_SUFFIX = "-redirect.entrypoints=web"
REDIRECT_MIDDLEWARE_SUFFIX = "-redirect.middlewares=redirect@file"


@pytest.fixture(autouse=True)
def _itsup_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve itsUP's install root to the per-test fixture tree."""
    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))


def copy_templates(tmp_path: Path) -> None:
    """Copy template files to test directory."""
    src_tpl = PROJECT_ROOT / "tpl"
    dst_tpl = tmp_path / "tpl"
    shutil.copytree(src_tpl, dst_tpl)


def test_generated_compose_files_are_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Generated docker-compose.yml must be valid YAML and pass docker compose config.

    FUNCTIONAL TEST - uses real docker compose validation.
    """
    # Setup minimal project structure
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    # Create minimal itsup.yml
    itsup_config = projects_dir / "itsup.yml"
    itsup_config.write_text("""
routerIP: 192.168.1.1
versions:
  traefik: v3.2
  crowdsec: v1.6.8
traefikDomain: traefik.example.com
crowdsec:
  enabled: false
  apikey: test-key
  collections: []
backup:
  enabled: false
""")

    # Create traefik.yml
    traefik_config = projects_dir / "traefik.yml"
    traefik_config.write_text("""
log:
  level: INFO
""")

    # Create test project directory
    test_project = projects_dir / "test-project"
    test_project.mkdir()

    # Create minimal docker-compose.yml
    compose_file = test_project / "docker-compose.yml"
    compose_file.write_text("""
services:
  web:
    image: nginx:alpine
    ports:
      - "3000:80"
""")

    # Create ingress.yml
    ingress_file = test_project / "ingress.yml"
    ingress_file.write_text("""
enabled: true
ingress:
  - service: web
    domain: test.example.com
    port: 80
    router: http
""")

    # Setup upstream directory
    upstream_dir = tmp_path / "upstream"
    upstream_dir.mkdir()

    # Create secrets directory
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "itsup.txt").write_text("TRAEFIK_ADMIN=admin:$apr1$xyz")

    # Change to tmp directory and mock paths
    monkeypatch.chdir(tmp_path)

    # Generate artifacts
    write_upstream("test-project")

    # Verify file exists
    generated_compose = upstream_dir / "test-project" / "docker-compose.yml"
    assert generated_compose.exists(), "Generated compose file should exist"

    # Parse as YAML (must not fail)
    with open(generated_compose) as f:
        compose_data = yaml.safe_load(f)

    assert compose_data is not None, "Compose file should be valid YAML"
    assert SERVICES_KEY in compose_data, "Compose should have services"
    assert WEB_SERVICE in compose_data["services"], "Should have web service"

    # Verify DNS honeypot was injected
    web_service = compose_data["services"]["web"]
    assert DNS_KEY in web_service, "Service should have DNS configured"
    assert DNS_HONEYPOT in web_service["dns"], f"Should use DNS honeypot {DNS_HONEYPOT}"

    # Verify Traefik labels were injected
    assert LABELS_KEY in web_service, "Service should have labels"
    labels = web_service["labels"]

    # Convert dict to list if needed for checking
    if isinstance(labels, dict):
        labels = [f"{k}={v}" for k, v in labels.items()]

    assert TRAEFIK_ENABLE in labels, "Should enable Traefik"

    # Find router rule label
    rule_labels = [l for l in labels if RULE_MARKER in l]
    assert len(rule_labels) > 0, "Should have router rule"
    assert TEST_DOMAIN in rule_labels[0], "Should route to configured domain"

    # Verify the companion plain-HTTP router redirects to HTTPS
    redirect_entrypoint_labels = [l for l in labels if l.endswith(REDIRECT_ENTRYPOINT_SUFFIX)]
    assert len(redirect_entrypoint_labels) == 1, "Should have one plain-HTTP redirect router"
    assert any(
        l.endswith(REDIRECT_MIDDLEWARE_SUFFIX) for l in labels
    ), "Redirect router should use the redirect@file middleware"

    # Verify proxynet network was added
    assert NETWORKS_KEY in compose_data, "Should have networks"
    assert PROXYNET in compose_data["networks"], "Should add proxynet"
    assert compose_data["networks"]["proxynet"]["external"] is True, "proxynet should be external"

    # Validate with docker compose config (if docker is available)
    # This is the real validation - docker compose will reject invalid files
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", str(generated_compose), "config"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # docker compose config should succeed (exit 0)
        if result.returncode != 0:
            pytest.fail(f"docker compose config failed:\n{result.stderr}")

    except FileNotFoundError:
        # Docker not available (e.g., in minimal CI), skip validation
        pytest.skip("Docker not available - skipping compose validation")


def test_dns_honeypot_consistency(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DNS honeypot IP must be consistent across all generated files.

    FUNCTIONAL TEST - verifies DNS constant usage.
    """
    # Setup minimal project structure
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    # Create minimal itsup.yml
    itsup_config = projects_dir / "itsup.yml"
    itsup_config.write_text("""
routerIP: 192.168.1.1
versions:
  traefik: v3.2
  crowdsec: v1.6.8
traefikDomain: traefik.example.com
crowdsec:
  enabled: false
  apikey: test-key
  collections: []
backup:
  enabled: false
""")

    # Create traefik.yml
    traefik_config = projects_dir / "traefik.yml"
    traefik_config.write_text("""
log:
  level: INFO
""")

    # Create test projects
    for i in range(3):
        test_project = projects_dir / f"project{i}"
        test_project.mkdir()

        # Create docker-compose.yml
        (test_project / "docker-compose.yml").write_text("""
services:
  web:
    image: nginx:alpine
  app:
    image: node:alpine
""")

        # Create ingress.yml
        (test_project / "ingress.yml").write_text("""
enabled: true
ingress: []
""")

    # Setup upstream directory
    upstream_dir = tmp_path / "upstream"
    upstream_dir.mkdir()

    # Create secrets directory
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "itsup.txt").write_text("TRAEFIK_ADMIN=admin:$apr1$xyz")

    # Copy template files to test directory
    copy_templates(tmp_path)

    # Change to tmp directory
    monkeypatch.chdir(tmp_path)

    # Generate artifacts for all projects
    for i in range(3):
        write_upstream(f"project{i}")

    # Also generate proxy compose
    write_proxy_compose()

    # Docker's embedded DNS, the only permitted fallback after the honeypot.
    docker_embedded_dns = "127.0.0.11"

    # Collect every service's DNS config (ordered) from generated files.
    dns_configs = []

    for i in range(3):
        compose_file = upstream_dir / f"project{i}" / "docker-compose.yml"
        with open(compose_file) as f:
            compose_data = yaml.safe_load(f)

        for service_config in compose_data["services"].values():
            if DNS_KEY in service_config:
                dns_configs.append(service_config["dns"])

    proxy_compose = tmp_path / "proxy" / "docker-compose.yml"
    if proxy_compose.exists():
        with open(proxy_compose) as f:
            proxy_data = yaml.safe_load(f)

        for service_config in proxy_data.get("services", {}).values():
            if DNS_KEY in service_config:
                dns_configs.append(service_config["dns"])

    assert dns_configs, "Expected at least one service with DNS configured"

    # Every service must query the honeypot FIRST, so all DNS is intercepted and logged.
    # Upstream services additionally list Docker's embedded DNS as a fallback for internal
    # name resolution; infra services use the honeypot alone. No other resolver is permitted
    # — a foreign IP, or the honeypot not being first, would let a service bypass logging.
    for dns in dns_configs:
        assert dns[0] == DNS_HONEYPOT, f"Honeypot {DNS_HONEYPOT} must be the first resolver, found: {dns}"
        assert set(dns) <= {
            DNS_HONEYPOT,
            docker_embedded_dns,
        }, f"Only the honeypot and Docker DNS are permitted resolvers, found: {dns}"


def test_generated_traefik_config_is_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Generated Traefik config must be valid YAML.

    Note: We can't use 'traefik --dry-run' without installing traefik binary,
    so we validate YAML structure instead.

    FUNCTIONAL TEST - validates YAML structure.
    """
    # Setup minimal project structure
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    # Create minimal itsup.yml
    itsup_config = projects_dir / "itsup.yml"
    itsup_config.write_text("""
routerIP: 192.168.1.1
versions:
  traefik: v3.2
traefik:
  domain: traefik.example.com
backup:
  enabled: false
""")

    # Create traefik.yml with some overrides
    traefik_config = projects_dir / "traefik.yml"
    traefik_config.write_text("""
log:
  level: DEBUG
api:
  dashboard: true
  insecure: false
""")

    # Setup directories
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "itsup.txt").write_text("TRAEFIK_ADMIN=admin:$apr1$xyz")

    # Copy template files to test directory
    copy_templates(tmp_path)

    # Change to tmp directory
    monkeypatch.chdir(tmp_path)

    # Import and run traefik config generation
    from bin.write_artifacts import write_traefik_config

    write_traefik_config()

    # Verify file exists
    traefik_yml = tmp_path / "proxy" / "traefik" / "traefik.yml"
    assert traefik_yml.exists(), "Generated traefik.yml should exist"

    # Parse as YAML (must not fail)
    with open(traefik_yml) as f:
        config_data = yaml.safe_load(f)

    assert config_data is not None, "Traefik config should be valid YAML"

    # Verify core structure
    assert ENTRYPOINTS_KEY in config_data, "Should have entryPoints"
    assert PROVIDERS_KEY in config_data, "Should have providers"

    # Verify user overrides were merged
    assert LOG_KEY in config_data, "Should have log config"
    assert config_data["log"]["level"] == LOG_LEVEL_DEBUG, "Should merge user log level"

    # Verify API config from overrides
    assert API_KEY in config_data, "Should have API config"
    assert config_data["api"]["dashboard"] is True, "Should merge API dashboard setting"
    assert config_data["api"]["insecure"] is False, "Should merge API insecure setting"


def test_external_host_http_ingress_generates_router(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An external-host HTTP passthrough (host set, plain port, no hostport) must
    generate a dynamic router pointing at host:port.

    Regression guard: the itsUP management API is an external host on 127.0.0.1:8888
    with router http and no hostport. A hostport-only filter in the HTTP router pass
    silently dropped it, leaving Traefik with no route (blanket 404). Containers still
    require hostport (they route via labels); external hosts must not.

    FUNCTIONAL TEST - validates generated router structure.
    """
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    (projects_dir / "itsup.yml").write_text("""
routerIP: 192.168.1.1
traefikDomain: traefik.example.com
versions:
  traefik: v3.2
backup:
  enabled: false
""")

    # External host, plain HTTP, no hostport — the API-route shape.
    api_project = projects_dir / "api-host"
    api_project.mkdir()
    (api_project / "itsup-project.yml").write_text("""
enabled: true
host: 127.0.0.1
ingress:
  - domain: api.example.com
    port: 8888
    router: http
""")

    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "itsup.txt").write_text("TRAEFIK_ADMIN=admin:$apr1$xyz")

    copy_templates(tmp_path)
    monkeypatch.chdir(tmp_path)

    from bin.write_artifacts import write_dynamic_routers

    write_dynamic_routers()

    routers_file = tmp_path / "proxy" / "traefik" / "dynamic" / "routers-http.yml"
    assert routers_file.exists(), "routers-http.yml should be generated"
    config = yaml.safe_load(routers_file.read_text())

    routers = config["http"]["routers"]
    services = config["http"]["services"]

    assert any(
        EXTERNAL_HOST_RULE in (r.get("rule") or "") for r in routers.values()
    ), f"external-host HTTP route missing from routers: {list(routers)}"
    backend_urls = [s["loadBalancer"]["servers"][0]["url"] for s in services.values()]
    assert EXTERNAL_HOST_BACKEND in backend_urls, f"backend not host:port: {backend_urls}"


def test_acme_challenge_passthrough_skips_redirect_router(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The ACME HTTP-01 passthrough carve-out (port 80, well-known challenge path)
    must not get a companion HTTPS-redirect router — that would redirect the
    challenge request before it reaches the backend serving it.
    """
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    (projects_dir / "itsup.yml").write_text("""
routerIP: 192.168.1.1
versions:
  traefik: v3.2
  crowdsec: v1.6.8
traefikDomain: traefik.example.com
crowdsec:
  enabled: false
  apikey: test-key
  collections: []
backup:
  enabled: false
""")

    test_project = projects_dir / "acme-project"
    test_project.mkdir()
    (test_project / "docker-compose.yml").write_text("""
services:
  web:
    image: nginx:alpine
""")
    (test_project / "itsup-project.yml").write_text("""
enabled: true
ingress:
  - service: web
    domain: test.example.com
    port: 80
    router: http
    passthrough: true
    path_prefix: /.well-known/acme-challenge/
""")

    (tmp_path / "upstream").mkdir()
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "itsup.txt").write_text("TRAEFIK_ADMIN=admin:$apr1$xyz")

    monkeypatch.chdir(tmp_path)
    write_upstream("acme-project")

    generated_compose = tmp_path / "upstream" / "acme-project" / "docker-compose.yml"
    compose_data = yaml.safe_load(generated_compose.read_text())
    labels = compose_data["services"]["web"]["labels"]

    assert not any(
        l.endswith(REDIRECT_ENTRYPOINT_SUFFIX) for l in labels
    ), "ACME challenge passthrough must not be redirected to HTTPS"
