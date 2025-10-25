"""Data loading from projects/ and secrets/"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Union, cast

import yaml
from dotenv import dotenv_values

from lib.models import Env, Ingress, IngressV2, Plugin, PluginRegistry, Project, Service, TraefikConfig

logger = logging.getLogger(__name__)

# === Models ===

class Ingress(BaseModel):
    """Traefik ingress rule"""
    service: str
    domain: str | None = None
    port: int = 80
    router: str = "http"
    path_prefix: str | None = None
    hostport: int | None = None
    passthrough: bool = False
    tls_sans: list[str] = []

class TraefikConfig(BaseModel):
    """Traefik routing configuration"""
    enabled: bool = True
    ingress: list[Ingress] = []

# === Secret Loading ===

def load_secrets() -> dict[str, str]:
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

def expand_env_vars(data: Any, secrets: dict[str, str]) -> Any:
    """Recursively expand ${VAR} in data structure"""
    if isinstance(data, dict):
        return {k: expand_env_vars(v, secrets) for k, v in data.items()}
    elif isinstance(data, list):
        return [expand_env_vars(item, secrets) for item in data]
    elif isinstance(data, str):
        # Expand ${VAR} and $VAR
        def replacer(match):
            var_name = match.group(1) or match.group(2)
            if var_name not in secrets:
                raise ValueError(f"Secret variable '{var_name}' not found in secrets")
            return secrets[var_name]

        pattern = r'\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)'
        return re.sub(pattern, replacer, data)
    else:
        return data

# === Project Loading ===

def load_infrastructure() -> dict:
    """Load infrastructure config from projects/traefik.yml"""
    traefik_file = Path("projects/traefik.yml")

    if not traefik_file.exists():
        logger.warning("projects/traefik.yml not found, using defaults")
        return {}

    with open(traefik_file) as f:
        config = yaml.safe_load(f)

    # Expand secrets
    secrets = load_secrets()
    config = expand_env_vars(config, secrets)

    return config

def load_project(project_name: str) -> tuple[dict, TraefikConfig]:
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

    with open(compose_file) as f:
        compose = yaml.safe_load(f)

    # Load traefik.yml
    traefik_file = project_dir / "traefik.yml"
    if not traefik_file.exists():
        logger.warning(f"No traefik.yml for {project_name}, using defaults")
        traefik = TraefikConfig()
    else:
        with open(traefik_file) as f:
            traefik_data = yaml.safe_load(f)
            traefik = TraefikConfig(**traefik_data)

    # Expand secrets in compose
    secrets = load_secrets()
    compose = expand_env_vars(compose, secrets)

    return compose, traefik

def list_projects() -> list[str]:
    """List all available projects"""
    projects_dir = Path("projects")
    if not projects_dir.exists():
        return []

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
