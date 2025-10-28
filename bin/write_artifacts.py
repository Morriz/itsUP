#!/usr/bin/env python3

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from jinja2 import Template

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.data import list_projects, load_project, validate_all, load_itsup_config, load_traefik_overrides
from lib.logging_config import setup_logging
from lib.models import Protocol, ProxyProtocol, Router

import logging
import yaml

load_dotenv()

logger = logging.getLogger(__name__)


def inject_traefik_labels(compose: dict, traefik_config, project_name: str) -> dict:
    """Inject Traefik labels into docker-compose services based on traefik.yml"""
    if not traefik_config.enabled:
        return compose

    services = compose.get("services", {})

    for ingress in traefik_config.ingress:
        service_name = ingress.service
        if service_name not in services:
            logger.warning(f"Service {service_name} in traefik.yml not found in docker-compose.yml")
            continue

        # Initialize labels if not present
        if "labels" not in services[service_name]:
            services[service_name]["labels"] = []

        labels = services[service_name]["labels"]
        if isinstance(labels, dict):
            # Convert dict to list format
            labels = [f"{k}={v}" for k, v in labels.items()]
            services[service_name]["labels"] = labels

        # Build Traefik labels
        # Make router name unique by including port to handle multiple ingress entries for same service
        router_name = f"{project_name}-{service_name}-{ingress.port}"

        # Enable Traefik (only once per service, not per ingress)
        if "traefik.enable=true" not in labels:
            labels.append("traefik.enable=true")

        # Router configuration
        if ingress.router == "http":
            # HTTP router
            labels.append(f"traefik.http.routers.{router_name}.entrypoints=web-secure")

            # Domain-based rule
            domains = []
            if ingress.tls and ingress.tls.main:
                # TLS with main + SANs
                domains = [ingress.tls.main] + ingress.tls.sans
            elif ingress.domain:
                # Legacy domain field
                domains = [ingress.domain]

            if domains:
                rule = " || ".join([f"Host(`{d}`)" for d in domains])
                if ingress.path_prefix:
                    rule += f" && PathPrefix(`{ingress.path_prefix}`)"
                labels.append(f"traefik.http.routers.{router_name}.rule={rule}")
                labels.append(f"traefik.http.routers.{router_name}.service={router_name}")
                labels.append(f"traefik.http.routers.{router_name}.tls=true")
                labels.append(f"traefik.http.routers.{router_name}.tls.certresolver=letsencrypt")

                # TLS domain configuration with SANs
                if ingress.tls and ingress.tls.main:
                    labels.append(f"traefik.http.routers.{router_name}.tls.domains[0].main={ingress.tls.main}")
                    for idx, san in enumerate(ingress.tls.sans):
                        labels.append(f"traefik.http.routers.{router_name}.tls.domains[0].sans[{idx}]={san}")

            # Service port
            labels.append(f"traefik.http.services.{router_name}.loadbalancer.server.port={ingress.port}")

            # Path prefix stripping middleware (if needed)
            # This would be added based on path_remove in IngressV2 if we add that field

        elif ingress.router == "tcp":
            # TCP router
            labels.append(f"traefik.tcp.routers.{router_name}.entrypoints=tcp-{ingress.hostport or ingress.port}")
            labels.append(f"traefik.tcp.routers.{router_name}.rule=HostSNI(`*`)")

            if ingress.passthrough:
                labels.append(f"traefik.tcp.routers.{router_name}.tls.passthrough=true")
            else:
                labels.append(f"traefik.tcp.routers.{router_name}.tls=true")

            labels.append(f"traefik.tcp.services.{router_name}.loadbalancer.server.port={ingress.port}")

        elif ingress.router == "udp":
            # UDP router
            labels.append(f"traefik.udp.routers.{router_name}.entrypoints=udp-{ingress.hostport or ingress.port}")
            labels.append(f"traefik.udp.services.{router_name}.loadbalancer.server.port={ingress.port}")

    return compose


def write_upstream(project_name: str) -> None:
    """Generate upstream/{project}/docker-compose.yml with Traefik labels injected"""
    logger.info(f"Generating upstream config for {project_name}")

    # Load project from projects/
    compose, traefik = load_project(project_name)

    # Inject Traefik labels
    compose = inject_traefik_labels(compose, traefik, project_name)

    # Merge proxynet network (required for Traefik discovery)
    if "networks" not in compose:
        compose["networks"] = {}

    # Add proxynet if not already present
    if "proxynet" not in compose["networks"]:
        compose["networks"]["proxynet"] = {
            "name": "proxynet",
            "external": True
        }

    # Ensure all services with Traefik labels are on proxynet
    services = compose.get("services", {})
    for service_name, service_config in services.items():
        labels = service_config.get("labels", [])
        # Check if service has traefik.enable=true label
        has_traefik = any("traefik.enable=true" in str(label) for label in labels)

        if has_traefik:
            if "networks" not in service_config:
                service_config["networks"] = []

            # Convert dict format to list if needed
            if isinstance(service_config["networks"], dict):
                service_config["networks"] = list(service_config["networks"].keys())

            # Add proxynet if not present
            if "proxynet" not in service_config["networks"]:
                service_config["networks"].append("proxynet")

    # Ensure upstream directory exists
    upstream_dir = Path("upstream") / project_name
    upstream_dir.mkdir(parents=True, exist_ok=True)

    # Write docker-compose.yml
    compose_file = upstream_dir / "docker-compose.yml"
    with open(compose_file, "w", encoding="utf-8") as f:
        yaml.dump(compose, f, indent=2, allow_unicode=True, default_flow_style=False, sort_keys=False)

    logger.info(f"Generated {compose_file}")


def write_upstreams() -> bool:
    """Generate all upstream/* directories from projects/

    Returns: True if all projects succeeded, False if any failed
    """
    projects = list_projects()

    if not projects:
        logger.warning("No projects found in projects/ directory")
        return True

    failed_projects = []
    for project_name in projects:
        try:
            write_upstream(project_name)
        except Exception as e:
            logger.error(f"Failed to generate upstream for {project_name}: {e}")
            failed_projects.append(project_name)

    if failed_projects:
        logger.error(f"Failed to generate upstream configs for: {', '.join(failed_projects)}")
        return False

    return True


def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override dict into base dict"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def write_traefik_config() -> None:
    """Generate proxy/traefik/traefik.yml from minimal template + user overrides"""
    logger.info("Generating proxy/traefik/traefik.yml")

    from lib.data import get_trusted_ips, load_traefik_overrides

    # Get trusted IPs for template
    trusted_ips_cidrs = get_trusted_ips()

    # Load minimal template
    with open("tpl/proxy/traefik.yml.j2", encoding="utf-8") as f:
        template_content = f.read()

    template = Template(template_content)

    # Render minimal base config (just structure + trustedIPs)
    config_content = template.render(
        trusted_ips_cidrs=trusted_ips_cidrs,
    )

    # Parse generated base config
    base_config = yaml.safe_load(config_content)

    # Load user overrides from projects/traefik.yml
    override_config = load_traefik_overrides()

    if override_config:
        logger.info("Merging user overrides from projects/traefik.yml")
        # Deep merge overrides ON TOP of base
        final_config = deep_merge(base_config, override_config)
    else:
        logger.warning("No projects/traefik.yml found - using minimal config only")
        final_config = base_config

    # Traefik expands {{ env "VAR" }} at runtime from environment
    # Variables are left as-is for Traefik to process

    # Ensure directory exists
    Path("proxy/traefik").mkdir(parents=True, exist_ok=True)

    # Write final config
    with open("proxy/traefik/traefik.yml", "w", encoding="utf-8") as f:
        yaml.dump(final_config, f, indent=2, allow_unicode=True, default_flow_style=False, sort_keys=False)

    logger.info("Generated proxy/traefik/traefik.yml")


def write_dynamic_routers() -> None:
    """Generate dynamic Traefik router configs"""
    logger.info("Generating dynamic router configs")

    from lib.data import get_trusted_ips, load_itsup_config, load_secrets, load_traefik_overrides

    # Load itsUP config for traefik domain
    itsup_config = load_itsup_config()
    traefik_config = itsup_config.get("traefik", {})
    if not traefik_config.get("domain"):
        raise ValueError(
            "Missing required config: projects/itsup.yml must have 'traefik.domain' field\n"
            "Example:\n"
            "  traefik:\n"
            "    domain: traefik.example.com"
        )
    traefik_domain = traefik_config["domain"]

    # Load secrets for template variables
    secrets = load_secrets()  # itsUP infrastructure secrets

    # Validate required secrets
    if "TRAEFIK_ADMIN" not in secrets:
        raise ValueError(
            "Missing required secret: TRAEFIK_ADMIN\n"
            "Add to secrets/itsup.txt or secrets/itsup.enc.txt\n"
            "Generate with: htpasswd -nb admin your-password"
        )

    # Load traefik overrides for plugin_registry
    traefik_overrides = load_traefik_overrides()
    plugin_registry = traefik_overrides.get("plugins", {})

    # Build project list in V1 format for templates
    all_project_names = list_projects()
    all_projects = []

    for project_name in all_project_names:
        compose, traefik = load_project(project_name)

        # Skip disabled projects
        if not traefik.enabled:
            continue

        # Include projects with ingress config (both external hosts and containers)
        # External hosts: no compose, but have traefik.host
        # Containers: have compose, may have ingress for passthrough/hostport
        if traefik.host:  # External host
            all_projects.append(
                {
                    "name": project_name,
                    "services": [
                        {"host": traefik.host, "image": None, "ingress": traefik.ingress}  # External host has no image
                    ],
                }
            )
        # TODO: Add container projects with passthrough/hostport ingress here if needed

    # Filter by router type for templates
    projects_http = []
    projects_tcp = []
    projects_udp = []

    for p in all_projects:
        http_services = []
        tcp_services = []
        udp_services = []

        for s in p["services"]:
            http_ingress = [i for i in s["ingress"] if i.router == "http"]
            tcp_ingress = [i for i in s["ingress"] if i.router == "tcp"]
            udp_ingress = [i for i in s["ingress"] if i.router == "udp"]

            if http_ingress:
                http_services.append({"host": s["host"], "image": s["image"], "ingress": http_ingress})
            if tcp_ingress:
                tcp_services.append({"host": s["host"], "image": s["image"], "ingress": tcp_ingress})
            if udp_ingress:
                udp_services.append({"host": s["host"], "image": s["image"], "ingress": udp_ingress})

        if http_services:
            projects_http.append({"name": p["name"], "services": http_services})
        if tcp_services:
            projects_tcp.append({"name": p["name"], "services": tcp_services})
        if udp_services:
            projects_udp.append({"name": p["name"], "services": udp_services})

    # Render HTTP routers using full template
    with open("tpl/proxy/routers-http.yml.j2", encoding="utf-8") as f:
        template_content = f.read()

    tpl_routers_http = Template(template_content)

    routers_http = tpl_routers_http.render(
        plugin_registry=plugin_registry,
        projects=projects_http,
        traefik_admin=secrets["TRAEFIK_ADMIN"],
        traefik_rule=f"Host(`{traefik_domain}`)",
        trusted_ips_cidrs=get_trusted_ips(),
    )

    # Render TCP routers using full template
    with open("tpl/proxy/routers-tcp.yml.j2", encoding="utf-8") as f:
        template_content = f.read()

    tpl_routers_tcp = Template(template_content)
    tpl_routers_tcp.globals["ProxyProtocol"] = ProxyProtocol  # Make enum available to template
    routers_tcp = tpl_routers_tcp.render(
        projects=projects_tcp,
    )

    # Render UDP routers
    with open("tpl/proxy/routers-udp.yml.j2", encoding="utf-8") as f:
        template_content = f.read()

    tpl_routers_udp = Template(template_content)
    routers_udp = tpl_routers_udp.render(
        projects=projects_udp,
    )

    # Ensure directory exists
    Path("proxy/traefik/dynamic").mkdir(parents=True, exist_ok=True)

    # Write router files
    with open("proxy/traefik/dynamic/routers-http.yml", "w", encoding="utf-8") as f:
        f.write(routers_http)

    with open("proxy/traefik/dynamic/routers-tcp.yml", "w", encoding="utf-8") as f:
        f.write(routers_tcp)

    with open("proxy/traefik/dynamic/routers-udp.yml", "w", encoding="utf-8") as f:
        f.write(routers_udp)

    logger.info(f"Generated dynamic routers for {len(all_projects)} external host projects")


def write_proxy_compose() -> None:
    """Generate proxy/docker-compose.yml from template"""
    logger.info("Generating proxy/docker-compose.yml")

    from lib.data import load_itsup_config, load_traefik_overrides

    # Load versions from itsup.yml (top-level versions key)
    itsup_config = load_itsup_config()
    versions = itsup_config.get("versions", {})
    traefik_version = versions.get("traefik", "v3.2")
    crowdsec_version = versions.get("crowdsec", "v1.6.8")

    # Load traefik overrides to check CrowdSec status
    traefik_config = load_traefik_overrides()

    # Check if CrowdSec is enabled
    crowdsec_plugin = traefik_config.get("experimental", {}).get("plugins", {}).get("bouncer", {})
    crowdsec_config = traefik_config.get("plugins", {}).get("crowdsec", {})

    crowdsec_enabled = bool(crowdsec_plugin and crowdsec_config.get("enabled", False))

    # Build template context
    context = {
        "versions": {
            "traefik": traefik_version,
            "crowdsec": crowdsec_version,
        },
        "traefik": {
            "crowdsec": {
                "enabled": crowdsec_enabled
            }
        },
        "plugin_registry": {
            "crowdsec": {
                "enabled": crowdsec_enabled,
                "collections": crowdsec_config.get("collections", []),
                "apikey": crowdsec_config.get("apikey"),
            }
        }
    }

    with open("tpl/proxy/docker-compose.yml.j2", encoding="utf-8") as f:
        template_content = f.read()

    template = Template(template_content)
    compose_content = template.render(**context)

    with open("proxy/docker-compose.yml", "w", encoding="utf-8") as f:
        f.write(compose_content)

    logger.info("Generated proxy/docker-compose.yml")


def write_proxy_artifacts() -> None:
    """Generate all proxy-related artifacts"""
    write_traefik_config()
    write_dynamic_routers()  # Dynamic routers (infrastructure + external hosts)
    write_proxy_compose()


if __name__ == "__main__":
    setup_logging()

    # Validate all projects first
    errors = validate_all()
    if errors:
        logger.error("Validation errors found:")
        for project, project_errors in errors.items():
            for error in project_errors:
                logger.error(f"  {project}: {error}")
        sys.exit(1)

    # Generate proxy artifacts (traefik config, routers, docker-compose)
    logger.info("Generating proxy artifacts...")
    write_proxy_artifacts()

    # Generate upstream configs
    logger.info("Generating upstream configs...")
    if not write_upstreams():
        logger.error("Failed to generate some upstream configs")
        sys.exit(1)

    logger.info("✅ All artifacts generated successfully")
