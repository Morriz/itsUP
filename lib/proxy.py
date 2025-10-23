import logging
import os
from typing import Callable, List

from dotenv import load_dotenv
from jinja2 import Template

from lib.data import get_plugin_registry, get_projects, get_versions
from lib.models import Plugin, Protocol, ProxyProtocol, Router
from lib.utils import run_command, run_command_output

load_dotenv()

logger = logging.getLogger(__name__)


def get_domains(filter: Callable[[Plugin], bool] = None) -> List[str]:
    """Get all domains in use"""
    projects = get_projects(filter)
    domains = set()

    for project in projects:
        for service in project.services:
            for ingress in service.ingress:
                if ingress.domain:
                    domains.add(ingress.domain)

                if ingress.tls:
                    domains.add(ingress.tls.main)

                    if ingress.tls.sans:
                        domains.update(ingress.tls.sans)

    return list(domains)


def write_routers() -> None:
    # we only get the stuff with passthrough or hostport + domain as the port 80/443 containers
    # have labels themselves and will be picked up dynamically
    projects_http = get_projects(
        filter=lambda _, s, i: i.router == Router.http
        and (i.passthrough or not s.image or (i.hostport and (i.domain or i.tls)))
    )
    with open("proxy/tpl/routers-http.yml.j2", encoding="utf-8") as f:
        t = f.read()
    tpl_routers_http = Template(t)
    domain = os.environ.get("TRAEFIK_DOMAIN")
    routers_http = tpl_routers_http.render(
        domain_suffix=os.environ.get("DOMAIN_SUFFIX"),
        plugin_registry=get_plugin_registry(),
        projects=projects_http,
        traefik_admin=os.environ.get("TRAEFIK_ADMIN"),
        traefik_rule=f"Host(`{domain}`)",
        trusted_ips_cidrs=os.environ.get("TRUSTED_IPS_CIDRS").split(","),
    )
    with open("proxy/traefik/dynamic/routers-http.yml", "w", encoding="utf-8") as f:
        f.write(routers_http)
    projects_tcp = get_projects(
        filter=lambda _, s, i: i.router == Router.tcp and (i.passthrough or not s.image or i.hostport)
    )
    with open("proxy/tpl/routers-tcp.yml.j2", encoding="utf-8") as f:
        t = f.read()
    tpl_routers_tcp = Template(t)
    tpl_routers_tcp.globals["ProxyProtocol"] = ProxyProtocol
    routers_tcp = tpl_routers_tcp.render(
        projects=projects_tcp,
    )
    with open("proxy/traefik/dynamic/routers-tcp.yml", "w", encoding="utf-8") as f:
        f.write(routers_tcp)
    projects_udp = get_projects(filter=lambda _, _2, i: i.router == Router.udp)
    with open("proxy/tpl/routers-udp.yml.j2", encoding="utf-8") as f:
        t = f.read()
    tpl_routers_udp = Template(t)
    routers_udp = tpl_routers_udp.render(projects=projects_udp)
    with open("proxy/traefik/dynamic/routers-udp.yml", "w", encoding="utf-8") as f:
        f.write(routers_udp)


def write_config() -> None:
    with open("proxy/tpl/traefik.yml.j2", encoding="utf-8") as f:
        t = f.read()
    tpl_config_http = Template(t)
    tpl_config_http.globals["Protocol"] = Protocol
    tpl_config_http.globals["Router"] = Router
    trusted_ips_cidrs = os.environ.get("TRUSTED_IPS_CIDRS").split(",")
    projects_hostport = get_projects(filter=lambda _, _2, i: i.hostport)
    plugin_registry = get_plugin_registry()
    has_plugins = any(plugin.enabled for _, plugin in plugin_registry)
    config_http = tpl_config_http.render(
        has_plugins=has_plugins,
        le_email=os.environ.get("LETSENCRYPT_EMAIL"),
        le_staging=bool(os.environ.get("LETSENCRYPT_STAGING")),
        plugin_registry=plugin_registry,
        projects=projects_hostport,
        trusted_ips_cidrs=trusted_ips_cidrs,
    )
    with open("proxy/traefik/traefik.yml", "w", encoding="utf-8") as f:
        f.write(config_http)


def write_compose() -> None:
    plugin_registry = get_plugin_registry()
    versions = get_versions()
    with open("proxy/tpl/docker-compose.yml.j2", encoding="utf-8") as f:
        t = f.read()
    tpl_compose = Template(t)
    tpl_compose.globals["Protocol"] = Protocol
    projects_hostport = get_projects(filter=lambda _, _2, i: bool(i.hostport))
    compose = tpl_compose.render(versions=versions, projects=projects_hostport, plugin_registry=plugin_registry)
    with open("proxy/docker-compose.yml", "w", encoding="utf-8") as f:
        f.write(compose)


def write_proxies() -> None:
    write_routers()
    write_config()
    write_compose()


def _service_needs_update(service: str) -> bool:
    """Check if a service's image or config changed"""
    try:
        # Get current config hash from docker-compose.yml
        current_hash = (
            run_command_output(["docker", "compose", "config", "--hash", service], cwd="proxy").strip().split()[1]
        )  # Output is "service hash"

        # Get running container's config hash from labels
        containers = (
            run_command_output(
                ["docker", "ps", "--filter", f"name=proxy-{service}", "--format", "{{.Names}}"], cwd="proxy"
            )
            .strip()
            .split("\n")
        )

        if not containers or not containers[0]:
            logger.info(f"No running containers for {service}")
            return True  # Service not running

        running_hash = run_command_output(
            [
                "docker",
                "inspect",
                containers[0],
                "--format",
                '{{index .Config.Labels "com.docker.compose.config-hash"}}',
            ],
            cwd="proxy",
        ).strip()

        if current_hash != running_hash:
            logger.info(f"{service} config changed: {running_hash[:12]} -> {current_hash[:12]}")
            return True

        logger.info(f"{service} config unchanged ({current_hash[:12]})")
        return False

    except Exception as e:
        logger.info(f"Error checking {service} update status: {e}")
        return True  # On error, assume update needed


def update_proxy(service: str = None) -> None:
    """Update proxy with zero-downtime rollout when changes detected"""
    logger.info("Updating proxy")
    run_command(["docker", "compose", "pull"], cwd="proxy")

    service = service or "traefik"

    # Check if service needs update
    if _service_needs_update(service):
        logger.info(f"Changes detected, rolling out {service}")
        run_command(["docker", "rollout", service], cwd="proxy")
    else:
        logger.info(f"No changes detected for {service}, skipping rollout")

    # Ensure all services are up
    run_command(["docker", "compose", "up", "-d"], cwd="proxy")
