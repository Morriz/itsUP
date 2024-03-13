import os
from logging import info
from typing import Dict, List

from dotenv import load_dotenv
from jinja2 import Template

from lib.data import get_plugin_registry, get_project, get_projects
from lib.models import Protocol
from lib.utils import run_command

load_dotenv()


def get_domains(project: str = None) -> List[str]:
    """Get all domains in use"""
    projects = get_projects(filter=lambda p, s: not s.passthrough and (not project or project == p.name))
    return [p.domain for p in projects if p.domain]


def get_internal_map() -> Dict[str, str]:
    domains = get_domains()
    return {d: "terminate:8443" for d in domains}


def get_terminate_map() -> Dict[str, str]:
    filtered = get_projects(
        filter=lambda p, s: bool(p.domain) and not s.passthrough and (not bool(p.entrypoint) or p.entrypoint == s.name)
    )
    return {
        p.domain: (f"{p.name}-" if p.entrypoint == s.name else "") + f"{s.name}:{s.port}"
        for p in filtered
        for s in p.services
    }


def get_passthrough_map() -> Dict[str, str]:
    filtered = get_projects(filter=lambda _, s: s.passthrough is True)
    return {p.domain: f"{s.name}:{s.port}" for p in filtered for s in p.services}


def write_maps() -> None:
    internal_map = get_internal_map()
    passthrough_map = get_passthrough_map()
    terminate_map = get_terminate_map()
    with open("proxy/tpl/map.conf.j2", encoding="utf-8") as f:
        t = f.read()
    tpl = Template(t)
    internal = tpl.render(map=internal_map)
    passthrough = tpl.render(map=passthrough_map)
    terminate = tpl.render(map=terminate_map)
    with open("proxy/nginx/map/internal.conf", "w", encoding="utf-8") as f:
        f.write(internal)
    with open("proxy/nginx/map/passthrough.conf", "w", encoding="utf-8") as f:
        f.write(passthrough)
    with open("proxy/nginx/map/terminate.conf", "w", encoding="utf-8") as f:
        f.write(terminate)


def write_proxy() -> None:
    project = get_project("home-assistant", throw=False)
    with open("proxy/tpl/proxy.conf.j2", encoding="utf-8") as f:
        t = f.read()
    tpl = Template(t)
    terminate = tpl.render(project=project)
    with open("proxy/nginx/proxy.conf", "w", encoding="utf-8") as f:
        f.write(terminate)


def write_terminate() -> None:
    domains = get_domains()
    with open("proxy/tpl/terminate.conf.j2", encoding="utf-8") as f:
        t = f.read()
    tpl = Template(t)
    terminate = tpl.render(domains=domains)
    with open("proxy/nginx/terminate.conf", "w", encoding="utf-8") as f:
        f.write(terminate)


def write_routers() -> None:
    projects_tcp = get_projects(
        filter=lambda p, s: s.protocol == Protocol.tcp and (not bool(p.entrypoint) or p.entrypoint == s.name)
    )
    with open("proxy/tpl/routers-web.yml.j2", encoding="utf-8") as f:
        t = f.read()
    tpl_routers_web = Template(t)
    domain = os.environ.get("TRAEFIK_DOMAIN")
    routers_web = tpl_routers_web.render(
        projects=projects_tcp,
        traefik_rule=f"Host(`{domain}`)",
        traefik_admin=os.environ.get("TRAEFIK_ADMIN"),
        plugin_registry=get_plugin_registry(),
        trusted_ips_cidrs=os.environ.get("TRUSTED_IPS_CIDRS").split(","),
    )
    with open("proxy/traefik/routers-web.yml", "w", encoding="utf-8") as f:
        f.write(routers_web)
    with open("proxy/tpl/routers-tcp.yml.j2", encoding="utf-8") as f:
        t = f.read()
    tpl_routers_tcp = Template(t)
    routers_tcp = tpl_routers_tcp.render(projects=projects_tcp, traefik_rule=f"HostSNI(`{domain}`)")
    with open("proxy/traefik/routers-tcp.yml", "w", encoding="utf-8") as f:
        f.write(routers_tcp)
    projects_udp = get_projects(filter=lambda _, s: s.protocol == Protocol.udp)
    with open("proxy/tpl/routers-udp.yml.j2", encoding="utf-8") as f:
        t = f.read()
    tpl_routers_tcp = Template(t)
    routers_tcp = tpl_routers_tcp.render(projects=projects_udp)
    with open("proxy/traefik/routers-udp.yml", "w", encoding="utf-8") as f:
        f.write(routers_tcp)


def write_config() -> None:
    with open("proxy/tpl/config-in.yml.j2", encoding="utf-8") as f:
        t = f.read()
    tpl_config_tcp = Template(t)
    tpl_config_tcp.globals["Protocol"] = Protocol
    trusted_ips_cidrs = os.environ.get("TRUSTED_IPS_CIDRS").split(",")
    projects_hostport = get_projects(filter=lambda _, s: bool(s.hostport))
    config_tcp = tpl_config_tcp.render(projects=projects_hostport, trusted_ips_cidrs=trusted_ips_cidrs)
    with open("proxy/traefik/config-in.yml", "w", encoding="utf-8") as f:
        f.write(config_tcp)
    with open("proxy/tpl/config-web.yml.j2", encoding="utf-8") as f:
        t = f.read()
    tpl_config_web = Template(t)
    plugin_registry = get_plugin_registry()
    has_plugins = any(plugin.enabled for _, plugin in plugin_registry)
    config_web = tpl_config_web.render(
        trusted_ips_cidrs=trusted_ips_cidrs,
        le_email=os.environ.get("LETSENCRYPT_EMAIL"),
        le_staging=bool(os.environ.get("LETSENCRYPT_STAGING")),
        plugin_registry=plugin_registry,
        has_plugins=has_plugins,
    )
    with open("proxy/traefik/config-web.yml", "w", encoding="utf-8") as f:
        f.write(config_web)


def write_compose() -> None:
    plugin_registry = get_plugin_registry()
    with open("proxy/tpl/docker-compose.yml.j2", encoding="utf-8") as f:
        t = f.read()
    tpl_compose = Template(t)
    tpl_compose.globals["Protocol"] = Protocol
    projects_hostport = get_projects(filter=lambda _, s: bool(s.hostport))
    compose = tpl_compose.render(projects=projects_hostport, plugin_registry=plugin_registry)
    with open("proxy/docker-compose.yml", "w", encoding="utf-8") as f:
        f.write(compose)


def write_proxies() -> None:
    write_maps()
    write_proxy()
    write_terminate()
    write_routers()
    write_config()
    write_compose()


def update_proxy(
    service: str = None,
) -> None:
    """Reload service(s) in the docker compose config for the proxy"""
    info(f"Updating proxy {service}")
    run_command(["docker", "compose", "pull"], cwd="proxy")
    run_command(["docker", "compose", "up", "-d"], cwd="proxy")
    # rollout_proxy(service)


def reload_proxy(service: str = None) -> None:
    info("Reloading proxy")
    # Execute docker compose command to reload nginx for both 'proxy' and 'terminate' services
    for s in [service] if service else ["proxy", "terminate"]:
        run_command(
            ["docker", "compose", "exec", s, "nginx", "-s", "reload"],
            cwd="proxy",
        )


def rollout_proxy(service: str = None) -> None:
    info(f"Rolling out proxy {service}")
    for s in [service] if service else ["proxy", "terminate"]:
        run_command(["docker", "rollout", s], cwd="proxy")
