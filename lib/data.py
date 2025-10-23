import importlib
import logging
from typing import Any, Callable, Dict, List, Union, cast

import yaml

from lib.models import Env, Ingress, Plugin, PluginRegistry, Project, Service

logger = logging.getLogger(__name__)


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
    logger.debug("Validating db.yml")
    db = get_db()
    plugins_raw = cast(Dict[str, Any], db["plugins"])
    for name, plugin in plugins_raw.items():
        model = get_plugin_model(name)
        p = {"name": name, **plugin}
        model.model_validate(p)
    for project in db["projects"]:
        Project.model_validate(project)


def get_versions() -> Dict[str, Any]:
    """Get versions of all images used in proxy setup"""
    logger.debug("Getting proxy image versions")
    db = get_db()
    return cast(Dict[str, Any], db["versions"])


def get_plugin_registry() -> PluginRegistry:
    """Get plugin registry."""
    logger.debug("Getting plugin registry")
    db = get_db()
    plugins_raw = cast(Dict[str, Any], db["plugins"])
    return PluginRegistry(**plugins_raw)


def get_plugins(filter: Callable[[Plugin], bool] = None) -> List[Plugin]:
    """Get all plugins. Optionally filter the results."""
    logger.debug("Getting plugins" + (f" with filter {filter}" if filter else ""))
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
    logger.debug("Getting projects" + (f" with filter {filter}" if filter else ""))
    db = get_db()
    projects_raw = cast(List[Dict[str, Any]], db["projects"])
    filtered_projects = []
    for project_dict in projects_raw:
        # Convert raw dictionary to Project object
        project = Project(**project_dict)

        # If no filter or filter matches project
        if not filter or filter.__code__.co_argcount == 1 and cast(Callable[[Project], bool], filter)(project):
            project.services = []
            for service_dict in project_dict["services"]:
                service = Service(**service_dict)
                service.ingress = [
                    Ingress(**ingress) for ingress in (service_dict["ingress"] if "ingress" in service_dict else [])
                ]
                project.services.append(service)
            filtered_projects.append(project)
            continue

        # Process services
        filtered_services = []
        for service_dict in project_dict["services"]:
            service = Service(**service_dict)

            if filter.__code__.co_argcount == 2 and cast(Callable[[Project, Service], bool], filter)(project, service):
                service.ingress = [
                    Ingress(**ingress) for ingress in (service_dict["ingress"] if "ingress" in service_dict else [])
                ]
                filtered_services.append(service)
                continue

            filtered_ingress = []
            for ingress_dict in service_dict["ingress"] if "ingress" in service_dict else []:
                ingress = Ingress(**ingress_dict)

                if filter.__code__.co_argcount == 3 and cast(Callable[[Project, Service, Ingress], bool], filter)(
                    project, service, ingress
                ):
                    filtered_ingress.append(ingress)

            if len(filtered_ingress) > 0:
                service.ingress = filtered_ingress
                filtered_services.append(service)

        if len(filtered_services) > 0:
            project.services = filtered_services
            filtered_projects.append(project)

    return filtered_projects


def write_projects(projects: List[Project]) -> None:
    """Write the projects to the db"""
    logger.debug(f"Writing {len(projects)} projects to the db")
    projects_dump = [p.model_dump(exclude_defaults=True, exclude_none=True, exclude_unset=True) for p in projects]
    write_db({"projects": projects_dump})


def get_project(name: str, throw: bool = True) -> Project:
    """Get a project by name. Optionally throw an error if not found (default)."""
    logger.debug(f"Getting project {name}")
    projects = get_projects()
    for item in projects:
        if item.name == name:
            return item
    error = f"Project {name} not found"
    logger.info(error)
    if throw:
        raise ValueError(error)
    return None


def upsert_project(project: Project) -> None:
    """Upsert a project"""
    logger.debug(f"Upserting project {project.name}: {project}")
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
    logger.debug(f"Getting services for project {project}" if project else "Getting all services")
    return [s for p in get_projects(lambda p: not bool(project) or p.name == project) for s in p.services]


def get_service(project: str | Project, service: str, throw: bool = True) -> Service:
    """Get a project's service by host"""
    logger.debug(f"Getting service {service} in project {project.name if isinstance(project, Project) else project}")
    p = get_project(project, throw) if isinstance(project, str) else project
    for item in p.services:
        if item.host == service:
            return item
    error = f"Service {service} not found in project {project}"
    logger.info(error)
    if throw:
        raise ValueError(error)
    return None


def upsert_service(project: str | Project, service: Service) -> None:
    """Upsert a service"""
    p = get_project(project) if isinstance(project, str) else project
    logger.debug(f"Upserting service {service.host} in project {p.name}: {service}")
    for i, s in enumerate(p.services):
        if s.host == service.host:
            p.services[i] = service
            break
    else:
        p.services.append(service)
    upsert_project(p)


def get_env(project: str | Project, service: str) -> Env:
    """Get a project's env by name"""
    proj_name = project.name if isinstance(project, Project) else project
    logger.debug(f"Getting env for service {service} in project {proj_name}")
    service = get_service(project, service)
    return service.env


def upsert_env(project: str | Project, service: str, env: Env) -> None:
    """Upsert the env of a service"""
    p = get_project(project) if isinstance(project, str) else project
    logger.debug(f"Upserting env for service {service} in project {p.name}: {env.model_dump_json()}")
    s = get_service(p, service)
    s.env = Env(**(s.env.model_dump() | env.model_dump()))
    upsert_service(project, s)
