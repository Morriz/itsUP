#!/usr/bin/env python3

"""Service operations (docker compose passthrough)"""

import logging
import subprocess
import sys
from pathlib import Path

import click
import yaml

from commands.common import complete_project
from lib.data import list_projects

logger = logging.getLogger(__name__)


def complete_svc_command(ctx, param, incomplete):
    """
    Smart completion for svc command arguments.

    Provides context-aware autocompletion:
    - First argument: docker compose commands (up, down, logs, etc.)
    - Subsequent arguments: service names from docker-compose.yml

    Args:
        ctx: Click context
        param: Click parameter
        incomplete: Partially typed string to complete

    Returns:
        List of commands or service names matching the incomplete string
    """
    # Get already-typed arguments
    args = ctx.params.get("command", [])
    project = ctx.params.get("project")

    # First argument after project: docker compose commands
    if len(args) == 0:
        commands = [
            "up",
            "down",
            "ps",
            "logs",
            "restart",
            "exec",
            "stop",
            "start",
            "config",
            "pull",
            "build",
            "kill",
            "rm",
            "pause",
            "unpause",
            "top",
        ]
        return [c for c in commands if c.startswith(incomplete)]

    # Second+ argument: service names from docker-compose.yml
    # (useful for: logs <service>, restart <service>, exec <service>, etc.)
    if project:
        compose_file = Path(f"upstream/{project}/docker-compose.yml")

        if compose_file.exists():
            try:
                with open(compose_file) as f:
                    compose = yaml.safe_load(f)
                    services = list(compose.get("services", {}).keys())
                    return [s for s in services if s.startswith(incomplete)]
            except yaml.YAMLError as e:
                logger.debug(f"Failed to parse compose file for autocomplete: {e}")
            except Exception as e:
                logger.debug(f"Unexpected error reading compose file for autocomplete: {e}")

    return []


@click.command(context_settings=dict(ignore_unknown_options=True, allow_interspersed_args=False))
@click.argument("project", autocompletion=complete_project)
@click.argument("command", nargs=-1, required=True, type=click.UNPROCESSED, autocompletion=complete_svc_command)
def svc(project, command):
    """
    Service operations (docker compose passthrough, no sync)

    Examples:
        itsup svc instrukt-ai ps           # Check status
        itsup svc instrukt-ai logs -f web  # Tail logs
        itsup svc instrukt-ai restart web  # Restart service
        itsup svc minio exec minio bash    # Shell into container

    Tab completion works for:
        - Project names
        - Docker compose commands
        - Service names
    """
    # Validate project exists
    projects = list_projects()
    if project not in projects:
        click.echo(f"Error: Project '{project}' not found", err=True)
        click.echo(f"Available: {', '.join(projects)}", err=True)
        sys.exit(1)

    # Run docker compose (no sync)
    upstream_dir = f"upstream/{project}"
    compose_file = f"{upstream_dir}/docker-compose.yml"

    cmd = ["docker", "compose", "--project-directory", upstream_dir, "-p", project, "-f", compose_file, *command]

    logger.debug(f"Running: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
