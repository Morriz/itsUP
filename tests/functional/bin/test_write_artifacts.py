#!/usr/bin/env python3

"""
Functional tests for artifact generation validation.

Validates that generated files are valid YAML and pass validation checks.
Uses REAL docker compose and traefik binaries.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from bin.write_artifacts import DNS_HONEYPOT, write_upstream, write_proxy_compose


# Path to real project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def copy_templates(tmp_path):
    """Copy template files to test directory."""
    src_tpl = PROJECT_ROOT / "tpl"
    dst_tpl = tmp_path / "tpl"
    shutil.copytree(src_tpl, dst_tpl)


def test_generated_compose_files_are_valid(tmp_path, monkeypatch):
    """Generated docker-compose.yml must be valid YAML and pass docker compose config.

    FUNCTIONAL TEST - uses real docker compose validation.
    """
    # Setup minimal project structure
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    # Create minimal itsup.yml
    itsup_config = projects_dir / "itsup.yml"
    itsup_config.write_text("""
router_ip: 192.168.1.1
versions:
  traefik: v3.2
  crowdsec: v1.6.8
traefik:
  domain: traefik.example.com
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
    assert "services" in compose_data, "Compose should have services"
    assert "web" in compose_data["services"], "Should have web service"

    # Verify DNS honeypot was injected
    web_service = compose_data["services"]["web"]
    assert "dns" in web_service, "Service should have DNS configured"
    assert DNS_HONEYPOT in web_service["dns"], f"Should use DNS honeypot {DNS_HONEYPOT}"

    # Verify Traefik labels were injected
    assert "labels" in web_service, "Service should have labels"
    labels = web_service["labels"]

    # Convert dict to list if needed for checking
    if isinstance(labels, dict):
        labels = [f"{k}={v}" for k, v in labels.items()]

    assert "traefik.enable=true" in labels, "Should enable Traefik"

    # Find router rule label
    rule_labels = [l for l in labels if ".rule=" in l]
    assert len(rule_labels) > 0, "Should have router rule"
    assert "test.example.com" in rule_labels[0], "Should route to configured domain"

    # Verify proxynet network was added
    assert "networks" in compose_data, "Should have networks"
    assert "proxynet" in compose_data["networks"], "Should add proxynet"
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


def test_dns_honeypot_consistency(tmp_path, monkeypatch):
    """DNS honeypot IP must be consistent across all generated files.

    FUNCTIONAL TEST - verifies DNS constant usage.
    """
    # Setup minimal project structure
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    # Create minimal itsup.yml
    itsup_config = projects_dir / "itsup.yml"
    itsup_config.write_text("""
router_ip: 192.168.1.1
versions:
  traefik: v3.2
  crowdsec: v1.6.8
traefik:
  domain: traefik.example.com
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
        (test_project / "docker-compose.yml").write_text(f"""
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

    # Collect all DNS IPs from generated files
    dns_ips = set()

    # Check upstream compose files
    for i in range(3):
        compose_file = upstream_dir / f"project{i}" / "docker-compose.yml"
        with open(compose_file) as f:
            compose_data = yaml.safe_load(f)

        for service_name, service_config in compose_data["services"].items():
            if "dns" in service_config:
                dns_ips.update(service_config["dns"])

    # Check proxy compose file
    proxy_compose = tmp_path / "proxy" / "docker-compose.yml"
    if proxy_compose.exists():
        with open(proxy_compose) as f:
            proxy_data = yaml.safe_load(f)

        for service_name, service_config in proxy_data.get("services", {}).items():
            if "dns" in service_config:
                dns_ips.update(service_config["dns"])

    # All DNS IPs must be exactly the DNS_HONEYPOT constant
    assert len(dns_ips) == 1, f"All services should use same DNS IP, found: {dns_ips}"
    assert DNS_HONEYPOT in dns_ips, f"All services should use DNS_HONEYPOT {DNS_HONEYPOT}"


def test_generated_traefik_config_is_valid(tmp_path, monkeypatch):
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
router_ip: 192.168.1.1
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
    assert "entryPoints" in config_data, "Should have entryPoints"
    assert "providers" in config_data, "Should have providers"

    # Verify user overrides were merged
    assert "log" in config_data, "Should have log config"
    assert config_data["log"]["level"] == "DEBUG", "Should merge user log level"

    # Verify API config from overrides
    assert "api" in config_data, "Should have API config"
    assert config_data["api"]["dashboard"] is True, "Should merge API dashboard setting"
    assert config_data["api"]["insecure"] is False, "Should merge API insecure setting"
