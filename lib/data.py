"""Data loading from projects/ and secrets/"""

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import netifaces
import yaml

from lib.models import TraefikConfig
from lib.sops import load_encrypted_env, load_env_file

logger = logging.getLogger(__name__)

# === V2 API Functions (for projects/ structure) ===


def load_secrets(project_name: str | None = None) -> dict[str, str]:
    """Load secrets from secrets/ (auto-detects encrypted .enc.txt or plaintext .txt)

    Auto-detection priority for each file:
    1. Try encrypted: secrets/{name}.enc.txt (decrypted with SOPS)
    2. Fall back to plaintext: secrets/{name}.txt (development only)

    Secret organization:
    - secrets/itsup.{enc.txt|txt} = itsUP infrastructure secrets (DNS, proxy, API)
    - secrets/{project}.{enc.txt|txt} = Project-specific secrets (one file per project)

    Args:
        project_name: Optional project name to load project-specific secrets.
                     If None, only loads itsup.{enc.txt|txt} for infrastructure.

    Returns:
        Dictionary of secret key-value pairs
    """
    secrets: dict[str, str] = {}
    secrets_dir = Path("secrets")

    if not secrets_dir.exists():
        logger.warning("secrets/ directory not found")
        return secrets

    def _load_secret_file(name: str) -> dict[str, str]:
        """Load secret file with auto-detection (encrypted first, then plaintext)"""
        encrypted_file = secrets_dir / f"{name}.enc.txt"
        plaintext_file = secrets_dir / f"{name}.txt"

        # Try encrypted first (production)
        if encrypted_file.exists():
            env_vars = load_encrypted_env(encrypted_file)
            if env_vars:
                logger.debug("Loaded %d secrets from %s.enc.txt (SOPS encrypted)", len(env_vars), name)
                return env_vars
            logger.warning("Failed to decrypt %s.enc.txt, trying plaintext...", name)

        # Fall back to plaintext (development)
        if plaintext_file.exists():
            env_vars = load_env_file(plaintext_file)
            logger.debug("Loaded %d secrets from %s.txt (plaintext - development only)", len(env_vars), name)
            if os.environ.get("PYTHON_ENV") == "production":
                logger.warning("⚠ Using plaintext secrets in production: %s.txt", name)
            return env_vars

        return {}

    # Load secrets based on context
    if project_name:
        # Project deployment: load ONLY project-specific secrets
        secrets.update(_load_secret_file(project_name))
    else:
        # Infrastructure: load ONLY itsup secrets
        secrets.update(_load_secret_file("itsup"))

    context = f" for {project_name}" if project_name else " for itsUP infrastructure"
    logger.info("Loaded %d secrets%s", len(secrets), context)
    return secrets


def get_env_with_secrets(project_name: str | None = None) -> dict[str, str]:
    """Build environment dict with secrets loaded

    This is the standard pattern for running docker compose commands that need secrets.
    Combines current environment with loaded secrets.

    Args:
        project_name: Optional project name to load project-specific secrets

    Returns:
        Dictionary combining os.environ with secrets (secrets override env)

    Example:
        env = get_env_with_secrets()
        subprocess.run(cmd, env=env, check=True)
    """
    secrets = load_secrets(project_name)
    return {**os.environ, **secrets}


def expand_env_vars(data: Any, secrets: dict[str, str]) -> Any:
    """Recursively expand ${VAR} in data structure

    Raises:
        ValueError: If a referenced variable is not found in secrets
    """
    if isinstance(data, dict):
        return {k: expand_env_vars(v, secrets) for k, v in data.items()}
    if isinstance(data, list):
        return [expand_env_vars(item, secrets) for item in data]
    if isinstance(data, str):
        # Expand ${VAR} and $VAR syntax
        # Pattern matches: ${VAR_NAME} or $VAR_NAME
        # Variable names must start with letter/underscore, followed by alphanumeric/underscore
        missing_vars = []

        def replacer(match: re.Match[str]) -> str:
            var_name = match.group(1) or match.group(2)
            if var_name not in secrets:
                missing_vars.append(var_name)
                return match.group(0)  # Keep original for error message
            return secrets[var_name]

        pattern = r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)"
        result = re.sub(pattern, replacer, data)

        if missing_vars:
            raise ValueError(
                f"Missing required secrets: {', '.join(missing_vars)}\n"
                f"  Add to secrets/itsup.txt or secrets/<project>.txt"
            )

        return result
    return data


def load_project(project_name: str) -> tuple[dict[str, Any], TraefikConfig]:
    """
    Load project from projects/{name}/

    Supports two types of projects:
    1. Container projects: have docker-compose.yml + optional ingress.yml
    2. External host passthroughs: have only ingress.yml (no containers)

    Args:
        project_name: Name of the project to load

    Returns: (docker_compose_dict, ingress_config)
        For external hosts, docker_compose_dict will be empty {}
        Secrets are left as ${VAR} placeholders for runtime expansion by Docker Compose
    """
    project_dir = Path("projects") / project_name

    if not project_dir.exists():
        raise FileNotFoundError(f"Project not found: {project_name}")

    # Load docker-compose.yml (optional for external host passthroughs)
    compose_file = project_dir / "docker-compose.yml"
    if compose_file.exists():
        with open(compose_file, encoding="utf-8") as f:
            compose = yaml.safe_load(f)
    else:
        # No docker-compose.yml - this is an ingress-only external host project
        compose = {}

    # Load ingress.yml
    ingress_file = project_dir / "ingress.yml"
    if not ingress_file.exists():
        if not compose:
            raise FileNotFoundError(f"Project {project_name} has neither docker-compose.yml nor ingress.yml")
        logger.warning("No ingress.yml for %s, using defaults", project_name)
        traefik = TraefikConfig()
    else:
        with open(ingress_file, encoding="utf-8") as f:
            traefik_data = yaml.safe_load(f)
            traefik = TraefikConfig(**traefik_data)

    # Secrets are left as ${VAR} for Docker Compose to expand at runtime
    return compose, traefik


def list_projects() -> list[str]:
    """List all available projects (both container and ingress-only)"""
    projects_dir = Path("projects")
    if not projects_dir.exists():
        return []

    return [
        p.name
        for p in projects_dir.iterdir()
        if p.is_dir()
        and ((p / "docker-compose.yml").exists() or (p / "ingress.yml").exists())
        and not p.name.startswith(".")
    ]


def validate_project(project_name: str) -> list[str]:
    """Validate project configuration, return list of errors"""
    errors = []

    try:
        compose, traefik = load_project(project_name)
    except Exception as e:
        return [str(e)]

    # Skip service validation for external host passthroughs (no compose)
    if not compose:
        # External host passthrough - only validate that host is set
        if not traefik.host:
            errors.append("External host project must have 'host' field in ingress.yml")
        return errors

    # Validate traefik references exist in compose (for container projects)
    services = compose.get("services", {})
    for ingress in traefik.ingress:
        if ingress.service not in services:
            errors.append(f"traefik.yml references unknown service: {ingress.service}")

    return errors


def validate_all() -> dict[str, list[str]]:
    """Validate all projects, return dict of project: [errors]"""
    results = {}
    for project in list_projects():
        errors = validate_project(project)
        if errors:
            results[project] = errors
    return results


def get_router_ip() -> str:
    """Get router IP from projects/itsup.yml or auto-detect"""

    # Try to load from projects/itsup.yml (top-level routerIP key)
    itsup_file = Path("projects/itsup.yml")
    if itsup_file.exists():
        with open(itsup_file, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
            router_ip = config.get("routerIP")
            if router_ip:
                logger.info("Using router IP from projects/itsup.yml: %s", router_ip)
                return router_ip

    # Auto-detect using netifaces
    try:
        gateways = netifaces.gateways()
        router_ip = gateways["default"][netifaces.AF_INET][0]
        logger.info("Auto-detected router IP: %s", router_ip)

        # Write back to projects/itsup.yml since it was empty
        update_itsup_yml_router_ip(router_ip)

        return router_ip
    except Exception as e:
        logger.error("Could not auto-detect router IP and none configured in projects/itsup.yml: %s", e)
        raise ValueError("Router IP required: set in projects/itsup.yml or ensure network detection works") from e


def update_itsup_yml_router_ip(ip: str) -> None:
    """Update projects/itsup.yml with detected router IP"""
    itsup_file = Path("projects/itsup.yml")

    if not itsup_file.exists():
        logger.warning("projects/itsup.yml not found, cannot update router IP")
        return

    # Read current content
    with open(itsup_file, encoding="utf-8") as f:
        content = f.read()

    # Replace the empty routerIP line with detected value
    updated = re.sub(
        r"(routerIP:)\s*$",
        f"routerIP: {ip}  # Auto-detected on {datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')}",
        content,
        flags=re.MULTILINE,
    )

    with open(itsup_file, "w", encoding="utf-8") as f:
        f.write(updated)

    logger.info("Updated projects/itsup.yml with router IP: %s", ip)


def get_trusted_ips() -> list[str]:
    """Build trusted IPs list for Traefik - ONLY router IP"""
    return [f"{get_router_ip()}/32"]


def load_itsup_config() -> dict[str, Any]:
    """Load projects/itsup.yml configuration

    Returns:
        Dictionary of itsUP configuration
        Secrets are left as ${VAR} placeholders - not expanded
    """
    itsup_file = Path("projects/itsup.yml")

    if not itsup_file.exists():
        logger.warning("projects/itsup.yml not found, using defaults")
        return {}

    with open(itsup_file, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    # Secrets are left as ${VAR} for safety
    return config


def load_traefik_overrides() -> dict[str, Any]:
    """Load projects/traefik.yml override configuration

    Returns:
        Dictionary of Traefik configuration overrides
        Secrets are left as ${VAR} placeholders - not expanded
    """
    traefik_file = Path("projects/traefik.yml")

    if not traefik_file.exists():
        logger.warning("projects/traefik.yml not found")
        return {}

    with open(traefik_file, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    # Secrets are left as ${VAR} for safety
    return config
