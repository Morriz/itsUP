import importlib
import inspect
from logging import debug, info
from modulefinder import Module
from typing import Any, Callable, Dict, List, Union, cast

import yaml

from lib.models import Env, Ingress, Plugin, PluginRegistry, Project, Service


def get_db() -> Dict[str, List[Dict[str, Any]] | Dict[str, Any]]:
    """Get the db"""
    with open("db.yml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def write_db(partial: Dict[str, List[Dict[str, Any]] | Dict[str, Any]]) -> None:
    """Write the db"""
    # get the db first
    db = get_db()
    # merge wwith partial
    db = {**db, **partial}
    with open("db.yml", "w", encoding="utf-8") as f:
        yaml.dump(db, f)


def get_plugin_model(name: str) -> type[Plugin]:
    """Get a model by name"""
    cls = f"Plugin{name.capitalize()}"
    try:
        model = importlib.import_module(f"lib.models.{cls}")
        return cast(type[Plugin], model)
    except ModuleNotFoundError:
        return Plugin


def validate_db() -> None:
    """Validate db.yml contents"""
    debug("Validating db.yml")
    db = get_db()
    plugins_raw = cast(Dict[str, Any], db["plugins"])
    for name, plugin in plugins_raw.items():
        model = get_plugin_model(name)
        p = {"name": name, **plugin}
        model.model_validate(p)
    for project in db["projects"]:
        Project.model_validate(project)


def get_plugin_registry() -> PluginRegistry:
    """Get plugin registry."""
    debug("Getting plugin registry")
    db = get_db()
    plugins_raw = cast(Dict[str, Any], db["plugins"])
    return PluginRegistry(**plugins_raw)


def get_plugins(filter: Callable[[Plugin], bool] = None) -> List[Plugin]:
    """Get all plugins. Optionally filter the results."""
    debug("Getting plugins" + (f" with filter {filter}" if filter else ""))
    registry = get_plugin_registry()
    plugins = []
    for name, p in registry:
        model = get_plugin_model(name=name)
        plugin = model(name=name, **p)
        if not filter or filter(plugin):
            plugins.append(plugin)
    return plugins


def get_projects(
    filter: Union[
        Callable[[Project, Service, Ingress], bool], Callable[[Project, Service], bool], Callable[[Project], bool]
    ] = None,
) -> List[Project]:
    """Get all projects. Optionally filter the results."""
    debug("Getting projects" + (f" with filter {filter}" if filter else ""))
    db = get_db()
    projects_raw = cast(List[Dict[str, Any]], db["projects"])
    ret = []
    for project in projects_raw:
        services = []
        p = Project(**project)
        if not filter or filter.__code__.co_argcount == 1 and cast(Callable[[Project], bool], filter)(p):
            ret.append(p)
            continue
        for s in p.services.copy():
            if filter.__code__.co_argcount == 2 and cast(Callable[[Project, Service], bool], filter)(p, s):
                services.append(s)
                continue
            ingress = []
            for i in s.ingress.copy():
                if filter.__code__.co_argcount == 3 and cast(Callable[[Project, Service, Ingress], bool], filter)(
                    p, s, i
                ):
                    ingress.append(i)
            if len(ingress) > 0:
                s.ingress = ingress
                services.append(s)
        if len(services) > 0:
            p.services = services
            ret.append(p)
    return ret


def write_projects(projects: List[Project]) -> None:
    """Write the projects to the db"""
    debug(f"Writing {len(projects)} projects to the db")
    projects_dump = [p.model_dump(exclude_defaults=True, exclude_none=True, exclude_unset=True) for p in projects]
    write_db({"projects": projects_dump})


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
    return [s for p in get_projects(lambda p: not bool(project) or p.name == project) for s in p.services]


def get_service(project: str | Project, service: str, throw: bool = True) -> Service:
    """Get a project's service by host"""
    debug(f"Getting service {service} in project {project.name if isinstance(project, Project) else project}")
    p = get_project(project, throw) if isinstance(project, str) else project
    for item in p.services:
        if item.host == service:
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
    return service.env


def upsert_env(project: str | Project, service: str, env: Env) -> None:
    """Upsert the env of a service"""
    p = get_project(project) if isinstance(project, str) else project
    debug(f"Upserting env for service {service} in project {p.name}: {env.model_dump_json()}")
    s = get_service(p, service)
    s.env = Env(**(s.env.model_dump() | env.model_dump()))
    upsert_service(project, s)


def upsert_service(project: str | Project, service: Service) -> None:
    """Upsert a service"""
    p = get_project(project) if isinstance(project, str) else project
    debug(f"Upserting service {service.host} in project {p.name}: {service}")
    for i, s in enumerate(p.services):
        if s.host == service.host:
            p.services[i] = service
            break
    else:
        p.services.append(service)
    upsert_project(p)
