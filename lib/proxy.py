import os
from logging import info
from typing import Dict, List

from dotenv import load_dotenv
from jinja2 import Template

from lib.data import get_plugin_registry, get_project, get_projects
from lib.models import Protocol, ProxyProtocol, Router
from lib.utils import run_command

load_dotenv()


def get_domains(project: str = None) -> List[str]:
    """Get all domains in use"""
    projects = get_projects(filter=lambda p, _, i: not i.passthrough and (not project or project == p.name))
    domains = []
    for p in projects:
        for s in p.services:
            for i in s.ingress:
                domains.append(i.domain)
    return domains


def get_internal_map() -> Dict[str, str]:
    domains = get_domains()
    return {d: "terminate:8443" for d in domains}


def get_terminate_map() -> Dict[str, str]:
    projects = get_projects(filter=lambda _, _2, i: not i.passthrough)
    map = {}
    for p in projects:
        for s in p.services:
            prefix = f"{p.name}-" if s.image else ""
            for i in s.ingress:
                map[i.domain] = f"{prefix}{s.host}:{i.port}"
    return map


def get_passthrough_map() -> Dict[str, str]:
    projects = get_projects(filter=lambda _, _2, i: i.passthrough)
    map = {}
    for p in projects:
        for s in p.services:
            for i in s.ingress:
                map[i.domain] = f"{s.host}:{i.port}"
    return map


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
    # we only get the stuff with passthrough or hostport + domain as the port 80/443 containers
    # have labels themselves and will be picked up dynamically
    projects_http = get_projects(
        filter=lambda _, s, i: i.router == Router.http and (i.passthrough or not s.image or (i.hostport and i.domain))
    )
    with open("proxy/tpl/routers-http.yml.j2", encoding="utf-8") as f:
        t = f.read()
    tpl_routers_http = Template(t)
    domain = os.environ.get("TRAEFIK_DOMAIN")
    routers_http = tpl_routers_http.render(
        projects=projects_http,
        traefik_rule=f"Host(`{domain}`)",
        traefik_admin=os.environ.get("TRAEFIK_ADMIN"),
        plugin_registry=get_plugin_registry(),
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
    routers_tcp = tpl_routers_tcp.render(projects=projects_tcp)
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
    trusted_ips_cidrs = os.environ.get("TRUSTED_IPS_CIDRS").split(",")
    projects_hostport = get_projects(filter=lambda _, _2, i: i.hostport)
    plugin_registry = get_plugin_registry()
    has_plugins = any(plugin.enabled for _, plugin in plugin_registry)
    config_http = tpl_config_http.render(
        has_plugins=has_plugins,
        domain_suffix=os.environ.get("DOMAIN_SUFFIX"),
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
    with open("proxy/tpl/docker-compose.yml.j2", encoding="utf-8") as f:
        t = f.read()
    tpl_compose = Template(t)
    tpl_compose.globals["Protocol"] = Protocol
    projects_hostport = get_projects(filter=lambda _, _2, i: bool(i.hostport))
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
