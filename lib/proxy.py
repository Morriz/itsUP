from typing import Dict

from jinja2 import Template

from lib.data import get_domains, get_project, get_services, get_terminate_services
from lib.utils import run_command


def get_internal_map() -> Dict[str, str]:
    filtered = get_terminate_services()
    return {svc.domain: "terminate:8443" for svc in filtered}


def get_terminate_map() -> Dict[str, str]:
    filtered = get_terminate_services()
    return {svc.domain: (f"{svc.project}-" if svc.upstream else "") + f"{svc.svc}:{svc.port}" for svc in filtered}


def get_passthrough_map() -> Dict[str, str]:
    filtered = get_services(filter=lambda p, s: s.passthrough)
    return {svc.domain: f"{svc.svc}:{svc.port}" for svc in filtered}


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


def reload_proxy(service: str = None) -> None:
    print("Reloading proxy")
    # Execute docker compose command to reload nginx for both 'proxy' and 'terminate' services
    for s in [service] if service else ["proxy", "terminate"]:
        run_command(
            ["docker", "compose", "exec", s, "nginx", "-s", "reload"],
            cwd="proxy",
        )


def rollout_proxy(service: str = None) -> None:
    print(f'Rolling out service "{service}"')
    for s in [service] if service else ["proxy", "terminate"]:
        run_command(
            ["docker", "rollout", s],
            cwd="proxy",
        )
