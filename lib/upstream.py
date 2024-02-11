import os
from typing import List

from jinja2 import Template

from lib.data import get_project, get_service, get_upstream_services
from lib.models import Service
from lib.utils import run_command


def write_upstream(project, services: List[Service]) -> None:
    with open("tpl/docker-compose.yml.j2", encoding="utf-8") as f:
        tpl = f.read()
    content = Template(tpl).render(project=project, services=services)
    with open(f"upstream/{project}/docker-compose.yml", "w", encoding="utf-8") as f:
        f.write(content)


def write_upstream_volume_folders(project: str, services: List[Service]) -> None:
    for svc in services:
        for path in svc.volumes:
            os.makedirs(f"upstream/{project}{path}", exist_ok=True)


def write_upstreams() -> None:

    for project, services in get_upstream_services(flatten=False).items():
        os.makedirs(f"upstream/{project}", exist_ok=True)
        write_upstream(project, services)
        write_upstream_volume_folders(project, services)


def check_upstream(project: str, service: str) -> None:
    """Check if upstream is running"""
    p = get_project(project)
    if not p:
        raise ValueError(f"Project {project} does not exist")
    s = get_service(project, service)
    if service and not s:
        print(f"Project {project} does not have service {service}")
        raise ValueError(f"Project {project} does not have service {service}")


def update_upstream(
    project: str,
    service: str = None,
    rollout: bool = False,
) -> None:
    """Reload service(s) in a docker compose config"""
    print(f"Updating upstream for project {project}")
    run_command(["docker", "compose", "up", "-d"], cwd=f"upstream/{project}")
    if not rollout:
        return
    for svc in get_upstream_services(project):
        if not service or svc.svc == service:
            rollout_service(project, service)


def update_upstreams(rollout: bool = False) -> None:
    for upstream_dir in [f.path for f in os.scandir("upstream") if f.is_dir()]:
        # get last item from path:
        project = upstream_dir.split("/")[-1]
        update_upstream(project, rollout)


def rollout_service(project: str, service: str):
    print(f'Rolling out service "{project}:{service}"')
    run_command(
        ["docker", "rollout", f"{project}-{service}"], cwd=f"upstream/{project}"
    )
