from typing import Callable, Dict, List

import yaml

from lib.models import Env, Project, Service


def get_db() -> Dict[str, List[Dict[str, str]]]:
    """Get the db"""
    with open("db.yml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_db() -> None:
    """Validate db.yml contents"""
    db = get_db()
    for project in db["projects"]:
        Project.model_validate(project)


def get_projects(filter: Callable[[Project, Service], bool] = None) -> List[Project]:
    """Get all projects. Optionally filter the results."""
    db = get_db()
    ret = []
    for p_json in db["projects"]:
        services = []
        p = Project(**p_json)
        for s in p.services:
            if not filter or filter(p, s):
                services.append(s)
        if len(services) > 0:
            p.services = services
            ret.append(p)
    return ret


def write_projects(projects: List[Project]) -> None:
    """Write the projects to the db"""
    with open("db.yml", "w", encoding="utf-8") as f:
        yaml.dump({"projects": projects}, f)


def get_project(name: str, throw: bool = True) -> Project:
    """Get a project by name. Optionally throw an error if not found (default)."""
    projects = get_projects()
    for item in projects:
        if item.name == name:
            return item
    error = f"Project {name} not found"
    print(error)
    if throw:
        raise ValueError(error)
    return None


def upsert_project(project: Project) -> None:
    """Upsert a project"""
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
    return [s for p in get_projects(lambda p, _: not bool(project) or p.name == project) for s in p.services]


def get_service(project: str | Project, service: str, throw: bool = True) -> Service:
    """Get a project's service by name"""
    p = get_project(project, throw) if isinstance(project, str) else project
    assert p is not None
    for item in p.services:
        if item.name == service:
            return item
    error = f"Service {service} not found in project {project}"
    print(error)
    if throw:
        raise ValueError(error)
    return None


def get_env(project: str | Project, service: str) -> Dict[str, str]:
    """Get a project's env by name"""
    service = get_service(project, service)
    assert service is not None
    return service.env


def upsert_env(project: str | Project, service: str, env: Env) -> None:
    """Upsert the env of a service"""
    p = get_project(project) if isinstance(project, str) else project
    assert p is not None
    s = get_service(p, service)
    assert s is not None
    s.env = Env(**(s.env.model_dump() | env.model_dump()))
    upsert_service(project, s)


def upsert_service(project: str | Project, service: Service) -> None:
    """Upsert a service"""
    p = get_project(project) if isinstance(project, str) else project
    assert p is not None
    for i, s in enumerate(p.services):
        assert s is not None
        if s.name == service.name:
            p.services[i] = service
            break
    else:
        p.services.append(service)
    upsert_project(p)
