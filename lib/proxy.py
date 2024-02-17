from logging import info
from typing import Dict, List

from jinja2 import Template

from lib.data import get_project, get_projects
from lib.utils import run_command


def get_domains(project: str = None) -> List[str]:
    """Get all domains in use"""
    projects = get_projects(filter=lambda _, s: not s.passthrough and (not project or project == s.name))
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
    with open("proxy/map/internal.conf", "w", encoding="utf-8") as f:
        f.write(internal)
    with open("proxy/map/passthrough.conf", "w", encoding="utf-8") as f:
        f.write(passthrough)
    with open("proxy/map/terminate.conf", "w", encoding="utf-8") as f:
        f.write(terminate)


def write_proxy() -> None:
    project = get_project("home-assistant", throw=False)
    with open("proxy/tpl/proxy.conf.j2", encoding="utf-8") as f:
        t = f.read()
    tpl = Template(t)
    terminate = tpl.render(project=project)
    with open("proxy/proxy.conf", "w", encoding="utf-8") as f:
        f.write(terminate)


def write_terminate() -> None:
    domains = get_domains()
    with open("proxy/tpl/terminate.conf.j2", encoding="utf-8") as f:
        t = f.read()
    tpl = Template(t)
    terminate = tpl.render(domains=domains)
    with open("proxy/terminate.conf", "w", encoding="utf-8") as f:
        f.write(terminate)


def write_nginx() -> None:
    write_maps()
    write_proxy()
    write_terminate()


def update_proxy(
    service: str = None,
) -> None:
    """Reload service(s) in the docker compose config for the proxy"""
    info(f"Updating proxy {service}")
    run_command(["docker", "compose", "pull"], cwd="proxy")
    run_command(["docker", "compose", "up", "-d"], cwd="proxy")
    rollout_proxy(service)


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
