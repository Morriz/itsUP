from logging import debug, info
from typing import Callable, Dict, List

import yaml

from lib.models import Env, Project, Service


def get_db() -> Dict[str, List[Dict[str, str]]]:
    """Get the db"""
    with open("db.yml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_db() -> None:
    """Validate db.yml contents"""
    debug("Validating db.yml")
    db = get_db()
    for project in db["projects"]:
        Project.model_validate(project)


def get_projects(filter: Callable[[Project, Service], bool] = None) -> List[Project]:
    """Get all projects. Optionally filter the results."""
    debug("Getting projects" + (f" with filter {filter}" if filter else ""))
    db = get_db()
    ret = []
    for p_json in db["projects"]:
        services = []
        p = Project(**p_json)
        for s in p.services.copy():
            if not filter or filter(p, s):
                services.append(s)
        if len(services) > 0:
            p.services = services
            ret.append(p)
    return ret


def write_projects(projects: List[Project]) -> None:
    """Write the projects to the db"""
    debug(f"Writing {len(projects)} projects to the db")
    projects_dump = [p.model_dump(exclude_defaults=True, exclude_none=True, exclude_unset=True) for p in projects]
    with open("db.yml", "w", encoding="utf-8") as f:
        yaml.dump({"projects": projects_dump}, f)


def get_project(name: str, throw: bool = True) -> Project:
    """Get a project by name. Optionally throw an error if not found (default)."""
    debug(f"Getting project {name}")
    projects = get_projects()
    for item in projects:
        if item.name == name:
            return item
    error = f"Project {name} not found"
    info(error)
    if throw:
        raise ValueError(error)
    return None


def upsert_project(project: Project) -> None:
    """Upsert a project"""
    debug(f"Upserting project {project.name}: {project}")
    projects = get_projects()
    # find the project in the list
    for i, p in enumerate(projects):
        if p.name == project.name:
            projects[i] = project
            break
    else:
        projects.append(project)
    write_projects(projects)


def get_services(project: str = None) -> List[Service]:
    """Get all services or just for a particular project."""
    debug(f"Getting services for project {project}" if project else "Getting all services")
    return [s for p in get_projects(lambda p, _: not bool(project) or p.name == project) for s in p.services]


def get_service(project: str | Project, service: str, throw: bool = True) -> Service:
    """Get a project's service by name"""
    debug(f"Getting service {service} in project {project.name if isinstance(project, Project) else project}")
    p = get_project(project, throw) if isinstance(project, str) else project
    assert p is not None
    for item in p.services:
        if item.name == service:
            return item
    error = f"Service {service} not found in project {project}"
    info(error)
    if throw:
        raise ValueError(error)
    return None


def get_env(project: str | Project, service: str) -> Dict[str, str]:
    """Get a project's env by name"""
    debug(f"Getting env for service {service} in project {project.name if isinstance(project, Project) else project}")
    service = get_service(project, service)
    assert service is not None
    return service.env


def upsert_env(project: str | Project, service: str, env: Env) -> None:
    """Upsert the env of a service"""
    p = get_project(project) if isinstance(project, str) else project
    debug(f"Upserting env for service {service} in project {p.name}: {env.model_dump_json()}")
    assert p is not None
    s = get_service(p, service)
    assert s is not None
    s.env = Env(**(s.env.model_dump() | env.model_dump()))
    upsert_service(project, s)


def upsert_service(project: str | Project, service: Service) -> None:
    """Upsert a service"""
    p = get_project(project) if isinstance(project, str) else project
    debug(f"Upserting service {service.name} in project {p.name}: {service}")
    assert p is not None
    for i, s in enumerate(p.services):
        assert s is not None
        if s.name == service.name:
            p.services[i] = service
            break
    else:
        p.services.append(service)
    upsert_project(p)
