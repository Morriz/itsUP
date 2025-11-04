#!/usr/bin/env python3

"""Service operations (docker compose passthrough)"""

import logging
import subprocess
import sys
from pathlib import Path

import click

from commands.common import complete_docker_compose_command, complete_project
from lib.data import get_env_with_secrets, list_projects
from lib.version_check import check_schema_version

logger = logging.getLogger(__name__)


@click.command(context_settings=dict(ignore_unknown_options=True, allow_interspersed_args=False))
@click.argument("project", shell_complete=complete_project)
@click.argument("command", nargs=-1, required=True, type=click.UNPROCESSED,
                shell_complete=complete_docker_compose_command("upstream/{project}/docker-compose.yml",
                                                                args_param_name="command",
                                                                project_param_name="project"))
def svc(project, command):
    """
    🔧 Service operations PROJECT COMMAND... (docker compose passthrough)

    Direct passthrough to docker compose for project service management.
    No regeneration - just runs docker compose commands directly.

    \b
    Examples:
        itsup svc instrukt-ai ps           # Check status
        itsup svc instrukt-ai logs -f web  # Tail logs
        itsup svc instrukt-ai restart web  # Restart service
        itsup svc minio exec minio bash    # Shell into container

    \b
    Tab completion works for:
        - Project names
        - Docker compose commands
        - Service names
    """
    check_schema_version()

    # Validate project exists
    projects = list_projects()
    if project not in projects:
        click.echo(f"Error: Project '{project}' not found", err=True)
        click.echo(f"Available: {', '.join(projects)}", err=True)
        sys.exit(1)

    # Run docker compose (no sync)
    upstream_dir = f"upstream/{project}"
    compose_file = f"{upstream_dir}/docker-compose.yml"

    # Auto-add -d flag for 'up' command (V1 compatibility)
    command_list = list(command)
    if command_list and command_list[0] == "up":
        # Don't add -d if user explicitly wants attached mode
        if not any(flag in command_list for flag in ["-d", "--detach", "--no-detach"]):
            command_list.insert(1, "-d")

    cmd = ["docker", "compose", "--project-directory", upstream_dir, "-p", project, "-f", compose_file, *command_list]

    logger.debug(f"Running: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, env=get_env_with_secrets(project), check=True)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
