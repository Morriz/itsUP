import os
from logging import info

from dotenv import load_dotenv
from jinja2 import Template

from lib.data import get_project, get_projects, get_service
from lib.models import Project
from lib.utils import run_command

load_dotenv()


def write_upstream(project: Project) -> None:
    with open("tpl/docker-compose.yml.j2", encoding="utf-8") as f:
        tpl = f.read()
    volumes = {}
    for s in project.services:
        vols = {}
        for i, v in enumerate(s.volumes):
            k = f"data_{s.name.replace('-', '_')}_{i}"
            vols[k] = v
        volumes[s.name] = vols

    if os.environ.get("PYTHON_ENV") != "production":
        content = Template(tpl).render(
            project=project, volumes=volumes, domain=os.environ.get("TRAEFIK_DOMAIN"), env="development"
        )
    else:
        content = Template(tpl).render(project=project, volumes=volumes, domain=project.domain)
    with open(f"upstream/{project.name}/docker-compose.yml", "w", encoding="utf-8") as f:
        f.write(content)


def write_upstream_volume_folders(project: Project) -> None:
    for s in project.services:
        for path in s.volumes:
            os.makedirs(f"upstream/{project.name}{path}", exist_ok=True)


def write_upstreams() -> None:
    # iterate over projects that have an entrypoint;
    for p in [project for project in get_projects() if project.entrypoint]:
        os.makedirs(f"upstream/{p.name}", exist_ok=True)
        write_upstream(p)
        write_upstream_volume_folders(p)


def check_upstream(project: str, service: str = None) -> None:
    """Check if upstream exists"""
    if not get_project(project):
        raise ValueError(f"Project {project} does not exist")
    if not service:
        return
    if not get_service(project, service):
        info(f"Project {project} does not have service {service}")
        raise ValueError(f"Project {project} does not have service {service}")


def update_upstream(
    project: str,
    service: str = None,
    rollout: bool = False,
) -> None:
    """Reload service(s) in a docker compose config"""
    info(f"Updating upstream for project {project}")
    run_command(["docker", "compose", "pull"], cwd=f"upstream/{project}")
    run_command(["docker", "compose", "up", "-d"], cwd=f"upstream/{project}")
    if not rollout:
        return
    # filter out the project by name and its services that should have an image
    projects = get_projects(filter=lambda p, s: p.name == project and bool(s.image))
    for p in projects:
        for s in p.services:
            if not service or s.name == service:
                rollout_service(project, s.name)


def update_upstreams(rollout: bool = False) -> None:
    for upstream_dir in [f.path for f in os.scandir("upstream") if f.is_dir()]:
        # get last item from path:
        project = upstream_dir.split("/")[-1]
        update_upstream(project, rollout=rollout)


def rollout_service(project: str, service: str) -> None:
    info(f'Rolling out service "{project}:{service}"')
    run_command(["docker", "rollout", f"{project}-{service}"], cwd=f"upstream/{project}")
