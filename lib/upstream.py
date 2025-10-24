import logging
import os
from typing import Any

import yaml
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader

from lib.data import get_project, get_projects, get_service
from lib.models import Project, Protocol, Router
from lib.utils import run_command

load_dotenv()

logger = logging.getLogger(__name__)


def to_yaml(value: Any, indent: int = 2) -> str:
    """Convert a value to human-readable YAML.

    Does one thing: Python object → YAML string.
    Indentation/positioning handled by template via |indent filter.
    """
    transformed = yaml.dump(value, indent=indent, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return transformed.rstrip("\n")


def write_upstream(project: Project) -> None:
    env = Environment(loader=FileSystemLoader("tpl/upstream"))
    env.globals["Protocol"] = Protocol
    env.globals["Router"] = Router
    env.globals["isinstance"] = isinstance
    env.globals["len"] = len
    env.globals["list"] = list
    env.globals["str"] = str
    env.filters["to_yaml"] = to_yaml
    tpl = env.get_template("docker-compose.yml.j2")
    content = tpl.render(project=project)
    with open(f"upstream/{project.name}/docker-compose.yml", "w", encoding="utf-8") as f:
        f.write(content)
    if project.env:
        env_content = "\n".join([f"{k}={v}" for k, v in project.env])
        with open(f"upstream/{project.name}/.env", "w", encoding="utf-8") as f:
            f.write(env_content)


def write_upstream_volume_folders(project: Project) -> None:
    for s in project.services:
        for path in s.volumes:
            # if occurences of colon > 1 then:
            if path.count(":") > 1:
                # strip parts such as :ro and :rw from the end first
                path = path.rsplit(":", 1)[0]
            # if path still contains colon, and starts with '/' or '../',
            # then we know its an existing host path, so skip
            if ":" in path and path.startswith("/") or path.startswith("../"):
                continue
            # check if it still has a colon, if so, split it and get the first part, else use the whole path
            path = path.split(":", 1)[0] if ":" in path else path
            # remove leading dot or add slash if
            path = path[1:] if path.startswith(".") else "/" + path if not path.startswith("/") else path
            os.makedirs(f"upstream/{project.name}{path}", exist_ok=True)


def write_upstreams() -> None:
    projects = get_projects(filter=lambda p, s: p.enabled and s.image)
    for p in projects:
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
        logger.info(f"Project {project} does not have service {service}")
        raise ValueError(f"Project {project} does not have service {service}")


def update_upstream(
    project: Project | str,
    service: str = None,
) -> None:
    """Reload service(s) in a docker compose config with zero-downtime rollout"""
    project = get_project(project, throw=True)
    logger.info(f"Updating upstream for project {project.name}")
    if project.enabled:
        run_command(["docker", "compose", "pull"], cwd=f"upstream/{project.name}")
        run_command(["docker", "compose", "up", "-d"], cwd=f"upstream/{project.name}")
    else:
        run_command(["docker", "compose", "down"], cwd=f"upstream/{project.name}")
        return
    # Only rollout stateless services (stateful services restarted via docker compose up -d above)
    projects = get_projects(filter=lambda p, s: p.enabled and p.name == project.name and bool(s.image))
    for p in projects:
        for s in p.services:
            if not service or s.host == service:
                if s.stateless:
                    rollout_service(project.name, s.host)
                else:
                    logger.info(f"Skipping rollout for {project.name}:{s.host} (stateless not set)")


def update_upstreams() -> None:
    for upstream_dir in [f.path for f in os.scandir("upstream") if f.is_dir()]:
        # get last item from path:
        project = upstream_dir.split("/")[-1]
        update_upstream(project)


def rollout_service(project: str, service: str) -> None:
    logger.info(f'Rolling out service "{project}:{service}"')
    run_command(["docker", "rollout", f"{project}-{service}"], cwd=f"upstream/{project}")
