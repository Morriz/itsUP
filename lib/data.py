from typing import Callable, Dict, List

import yaml

from lib.models import Project, Service


def get_projects() -> List[Project]:
    """Get all projects"""
    with open("db.yml", encoding="utf-8") as f:
        db = yaml.safe_load(f)
    return [Project(**p) for p in db["projects"]]


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


def get_services(
    project: str = None,
    filter: Callable[[Project, Service], bool] = None,
) -> List[Service]:
    """
    Get all projects with their services, or just the services for a project.
    Optionally filter the services, and flatten the list.
    """
    projects = get_projects()
    services = []
    for p in projects:
        if project and p.name != project:
            continue
        for svc in p.services:
            # first add some derived props
            svc.domain = p.domain  # we set it here as this is the main data getter
            svc.project = p.name
            if p.upstream == svc.svc:
                svc.upstream = True
            if not filter or filter(p, svc):
                services.append(svc)
    return services


def get_service(project: str | Project, service: str, throw: bool = True) -> Service:
    """Get a project's service by name"""
    p = get_project(project, throw) if isinstance(project, str) else project
    assert p is not None
    for item in p.services:
        if item.svc == service:
            return item
    error = f"Service {service} not found in project {project}"
    print(error)
    if throw:
        raise ValueError(error)
    return None


def get_env(project: str | Project, svc: str) -> Dict[str, str]:
    """Get a project's env by name"""
    service = get_service(project, svc)
    assert service is not None
    return service.env


def upsert_env(project: str | Project, svc: str, env: Dict[str, str]) -> None:
    """Upsert the env of a service"""
    p = get_project(project) if isinstance(project, str) else project
    assert p is not None
    s = get_service(p, svc)
    assert s is not None
    s.env = s.env | env
    upsert_service(project, s)


def upsert_service(project: str | Project, service: Service) -> None:
    """Upsert a service"""
    p = get_project(project) if isinstance(project, str) else project
    assert p is not None
    for i, s in enumerate(p.services):
        assert s is not None
        if s.svc == service.svc:
            p.services[i] = service
            break
    else:
        p.services.append(service)
    upsert_project(p)


def get_terminate_services() -> List[Service]:
    return get_services(filter=lambda p, s: not s.passthrough and not (p.upstream and not s.upstream))


def get_domains() -> List[str]:
    """Get all domains in use"""
    services = get_terminate_services()
    return [svc.domain for svc in services if svc.domain]


def get_upstream_services(project: str = None) -> List[Service]:
    """Get all services that are running upstream"""
    return get_services(project, filter=(lambda _, s: bool(s.image)))
