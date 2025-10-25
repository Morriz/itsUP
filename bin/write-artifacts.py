#!.venv/bin/python

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.data import list_projects, load_project, validate_all
from lib.logging_config import setup_logging
from lib.proxy import write_proxies

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
        router_name = f"{project_name}-{service_name}"

        # Enable Traefik
        labels.append("traefik.enable=true")

        # Router configuration
        if ingress.router == "http":
            # HTTP router
            labels.append(f"traefik.http.routers.{router_name}.entrypoints=websecure")

            # Domain-based rule
            if ingress.domain:
                rule = f"Host(`{ingress.domain}`)"
                if ingress.path_prefix:
                    rule += f" && PathPrefix(`{ingress.path_prefix}`)"
                labels.append(f"traefik.http.routers.{router_name}.rule={rule}")
                labels.append(f"traefik.http.routers.{router_name}.tls=true")
                labels.append(f"traefik.http.routers.{router_name}.tls.certresolver=letsencrypt")

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

    # Ensure upstream directory exists
    upstream_dir = Path("upstream") / project_name
    upstream_dir.mkdir(parents=True, exist_ok=True)

    # Write docker-compose.yml
    compose_file = upstream_dir / "docker-compose.yml"
    with open(compose_file, "w", encoding="utf-8") as f:
        yaml.dump(compose, f, indent=2, allow_unicode=True, default_flow_style=False, sort_keys=False)

    logger.info(f"Generated {compose_file}")


def write_upstreams() -> None:
    """Generate all upstream/* directories from projects/"""
    projects = list_projects()

    if not projects:
        logger.warning("No projects found in projects/ directory")
        return

    for project_name in projects:
        try:
            write_upstream(project_name)
        except Exception as e:
            logger.error(f"Failed to generate upstream for {project_name}: {e}")


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

    # Generate proxy configs
    write_proxies()

    # Generate upstream configs
    write_upstreams()

    logger.info("All artifacts generated successfully")
