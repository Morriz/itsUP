"""Project scaffolding logic for 'itsup create'."""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

RESERVED_NAMES = {"dns", "proxy", "traefik", "itsup", "monitor", "api"}

NAME_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


def validate_project_name(name: str) -> None:
    """Validate a project name.

    Raises:
        ValueError: If the name is invalid.
    """
    if not name:
        raise ValueError("Project name cannot be empty")

    if len(name) > 63:
        raise ValueError(f"Project name too long ({len(name)} chars, max 63)")

    if name in RESERVED_NAMES:
        raise ValueError(f"Project name '{name}' is reserved ({', '.join(sorted(RESERVED_NAMES))})")

    if not NAME_PATTERN.match(name):
        raise ValueError("Project name must be lowercase alphanumeric with hyphens (no leading/trailing hyphens)")


def create_project(name: str, root: Path | None = None) -> None:
    """Scaffold a new project with config files and empty secrets.

    Creates:
        - projects/<name>/itsup-project.yml
        - projects/<name>/docker-compose.yml
        - secrets/<name>.txt (if not exists)

    Args:
        name: Project name (validated).
        root: Project root directory. Defaults to cwd.

    Raises:
        ValueError: If name is invalid or project already exists.
    """
    validate_project_name(name)

    if root is None:
        root = Path(".")

    projects_dir = root / "projects"
    secrets_dir = root / "secrets"
    project_path = projects_dir / name

    if project_path.exists():
        raise ValueError(f"Project '{name}' already exists at {project_path}")

    # Create project directory
    project_path.mkdir(parents=True)

    # itsup-project.yml
    itsup_yml = project_path / "itsup-project.yml"
    itsup_yml.write_text(
        f"enabled: true\n"
        f"ingress:\n"
        f"  - service: {name}-web\n"
        f"    router: http\n"
        f"    port: 80\n"
        f"    domain: {name}.srv.instrukt.ai\n"
    )
    logger.info("Created %s", itsup_yml)

    # docker-compose.yml
    compose_yml = project_path / "docker-compose.yml"
    compose_yml.write_text(
        f"services:\n"
        f"  {name}-web:\n"
        f"    image: nginx:alpine\n"
        f"    restart: unless-stopped\n"
        f"    expose:\n"
        f"      - 80\n"
        f"    networks:\n"
        f"      - default\n"
        f"    healthcheck:\n"
        f'      test: ["CMD", "curl", "-f", "http://localhost:80"]\n'
        f"      interval: 30s\n"
        f"      timeout: 10s\n"
        f"      retries: 3\n"
    )
    logger.info("Created %s", compose_yml)

    # secrets file (only if not exists)
    secret_file = secrets_dir / f"{name}.txt"
    if not secret_file.exists():
        secrets_dir.mkdir(parents=True, exist_ok=True)
        secret_file.write_text(f"# Secrets for {name}\n# KEY=value\n")
        logger.info("Created %s", secret_file)
    else:
        logger.warning("Secrets file %s already exists (not overwritten)", secret_file)
