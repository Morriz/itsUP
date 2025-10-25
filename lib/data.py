import importlib
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Union, cast

import yaml
from dotenv import dotenv_values

from lib.models import Env, Ingress, IngressV2, Plugin, PluginRegistry, Project, Service, TraefikConfig

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


# === V2 API Functions (for projects/ structure) ===


def load_secrets() -> Dict[str, str]:
    """Load all secrets from secrets/ (decrypted .txt files)"""
    secrets = {}
    secrets_dir = Path("secrets")

    if not secrets_dir.exists():
        logger.warning("secrets/ directory not found")
        return secrets

    # Load global secrets first
    global_file = secrets_dir / "global.txt"
    if global_file.exists():
        secrets.update(dotenv_values(global_file))

    # Load project-specific secrets
    for secret_file in secrets_dir.glob("*.txt"):
        if secret_file.name in ("global.txt", "README.txt"):
            continue
        secrets.update(dotenv_values(secret_file))

    logger.info(f"Loaded {len(secrets)} secrets")
    return secrets


def expand_env_vars(data: Any, secrets: Dict[str, str]) -> Any:
    """Recursively expand ${VAR} in data structure"""
    if isinstance(data, dict):
        return {k: expand_env_vars(v, secrets) for k, v in data.items()}
    elif isinstance(data, list):
        return [expand_env_vars(item, secrets) for item in data]
    elif isinstance(data, str):
        # Expand ${VAR} and $VAR
        def replacer(match):
            var_name = match.group(1) or match.group(2)
            return secrets.get(var_name, match.group(0))

        pattern = r"\$\{([^}]+)\}|\$([A-Z_][A-Z0-9_]*)"
        return re.sub(pattern, replacer, data)
    else:
        return data


def load_infrastructure() -> Dict[str, Any]:
    """Load infrastructure config from projects/traefik.yml"""
    traefik_file = Path("projects/traefik.yml")

    if not traefik_file.exists():
        logger.warning("projects/traefik.yml not found, using defaults")
        return {}

    with open(traefik_file, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Expand secrets
    secrets = load_secrets()
    config = expand_env_vars(config, secrets)

    return config


def load_project(project_name: str) -> tuple[Dict[str, Any], TraefikConfig]:
    """
    Load project from projects/{name}/

    Returns: (docker_compose_dict, traefik_config)
    """
    project_dir = Path("projects") / project_name

    if not project_dir.exists():
        raise FileNotFoundError(f"Project not found: {project_name}")

    # Load docker-compose.yml
    compose_file = project_dir / "docker-compose.yml"
    if not compose_file.exists():
        raise FileNotFoundError(f"Missing docker-compose.yml for {project_name}")

    with open(compose_file, encoding="utf-8") as f:
        compose = yaml.safe_load(f)

    # Load traefik.yml
    traefik_file = project_dir / "traefik.yml"
    if not traefik_file.exists():
        logger.warning(f"No traefik.yml for {project_name}, using defaults")
        traefik = TraefikConfig()
    else:
        with open(traefik_file, encoding="utf-8") as f:
            traefik_data = yaml.safe_load(f)
            traefik = TraefikConfig(**traefik_data)

    # Expand secrets in compose
    secrets = load_secrets()
    compose = expand_env_vars(compose, secrets)

    return compose, traefik


def list_projects() -> List[str]:
    """List all available projects"""
    projects_dir = Path("projects")
    if not projects_dir.exists():
        return []

    return [
        p.name
        for p in projects_dir.iterdir()
        if p.is_dir() and (p / "docker-compose.yml").exists() and p.name != ".git"  # Exclude .git directory
    ]


def validate_project(project_name: str) -> List[str]:
    """Validate project configuration, return list of errors"""
    errors = []

    try:
        compose, traefik = load_project(project_name)
    except Exception as e:
        return [str(e)]

    # Validate traefik references exist in compose
    services = compose.get("services", {})
    for ingress in traefik.ingress:
        if ingress.service not in services:
            errors.append(f"traefik.yml references unknown service: {ingress.service}")

    return errors


def validate_all() -> Dict[str, List[str]]:
    """Validate all projects, return dict of project: [errors]"""
    results = {}
    for project in list_projects():
        errors = validate_project(project)
        if errors:
            results[project] = errors
    return results
