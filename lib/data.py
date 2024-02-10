from typing import Dict, List, Union

import yaml

from lib.models import Project, Service


def get_projects() -> Dict[str, List[Project]]:
    """Get all projects"""
    with open("db.yml", encoding="utf-8") as f:
        db = yaml.safe_load(f)
    return [Project(**p) for p in db["projects"]]


def write_projects(projects: List[Project]):
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


def upsert_project(project: Project):
    """Upsert a project"""
    projects = get_projects()
    # find the project in the list
    for i, p in enumerate(projects):
        if p.name == project.name:
            projects[i] = projects
            break
    else:
        projects.append(project)
    write_projects(projects)


def get_services(
    project: str = None,
    filter: Dict[str, str] = None,
    flatten: bool = True,
) -> List[Service]:
    """
    Get all projects with their services, or just the services for a project.
    Optionally filter the services, and flatten the list.
    """
    projects: List[Project] = get_projects()
    ret = {}
    # first add some derived props
    for p in projects:
        services = []
        for svc in p.services:
            svc.domain = p.domain  # we set it here as this is the main data getter
            svc.project = p.name
            if p.upstream == svc.svc:
                svc.upstream = True
            services.append(svc)
        ret[p.name] = services
    if filter:
        filtered = {}
        for p, services in ret.items():
            bag = []
            for svc in services:
                if filter(get_project(p), svc):
                    bag.append(svc)
            if len(bag) > 0:
                filtered[p] = bag
        ret = filtered
    if project:
        return ret[project]
    if flatten:
        return [svc for services in ret.values() for svc in services]
    return ret


def get_service(
    project: Union[str, Project], service: str, throw: bool = True
) -> Project:
    """Get a project's service by name"""
    project = get_project(project) if isinstance(project, str) else project
    for item in project.services:
        if item.svc == service:
            return item
    error = f"Service {service} not found in project {project}"
    print(error)
    if throw:
        raise ValueError(error)


def get_env(project: Union[str, Project], svc: str) -> Dict[str, str]:
    """Get a project's env by name"""
    service = get_service(project, svc)
    return service.env


def upsert_env(project: Union[str, Project], svc: str, env: Dict[str, str]):
    """Upsert the env of a service"""
    p = get_project(project)
    s = get_service(p, svc)
    s.env = s.env | env
    upsert_service(project, s)


def upsert_service(project: Union[str, Project], service: Service):
    """Upsert a service"""
    project = get_project(project)
    # find the project in the list
    for i, s in enumerate(project.services):
        if s.svc == service.svc:
            project.services[i] = service
            break
    else:
        project.services.append(service)
    upsert_project(project)


def get_terminate_services() -> Dict[str, str]:
    return get_services(
        filter=lambda p, s: not s.passthrough and not (p.upstream and not s.upstream)
    )


def get_domains() -> List[str]:
    """Get all domains in use"""
    services = get_terminate_services()
    return [svc.domain for svc in services]


def get_upstream_services(project: str = None, flatten: bool = True) -> List[Service]:
    """Get all services that are running upstream"""
    filtered = get_services(project, filter=lambda p, s: s.image, flatten=flatten)
    return filtered
