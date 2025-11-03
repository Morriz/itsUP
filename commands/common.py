#!/usr/bin/env python3

"""Common utilities for CLI commands"""

import logging
import subprocess
from pathlib import Path

import yaml

from lib.data import list_projects

logger = logging.getLogger(__name__)


def complete_project(ctx, param, incomplete):
    """
    Autocomplete project names.

    Args:
        ctx: Click context
        param: Click parameter
        incomplete: Partially typed string to complete

    Returns:
        List of project names matching the incomplete string
    """
    return [p for p in list_projects() if p.startswith(incomplete)]


def complete_stack_or_project(ctx, param, incomplete):
    """
    Autocomplete infrastructure stacks (dns, proxy) or project names.

    Args:
        ctx: Click context
        param: Click parameter
        incomplete: Partially typed string to complete

    Returns:
        List of stack names and project names matching the incomplete string
    """
    stacks = ['dns', 'proxy']
    projects = list_projects()
    all_options = stacks + projects
    return [opt for opt in all_options if opt.startswith(incomplete)]


def complete_docker_compose_command(compose_file_path: str, args_param_name: str = "args", project_param_name: str = None):
    """
    Create a completion function for docker compose commands and service names.

    This factory function returns a completion function that provides:
    - First argument: docker compose commands (up, down, logs, etc.)
    - Subsequent arguments: service names from docker-compose.yml

    Args:
        compose_file_path: Path to the docker-compose.yml file (can use {project} placeholder)
        args_param_name: Name of the parameter containing args (default: "args")
        project_param_name: Optional name of project parameter for dynamic path (default: None)

    Returns:
        Completion function for use with Click's shell_complete parameter
    """
    def _complete(ctx, param, incomplete):
        # Get already-typed arguments
        args = ctx.params.get(args_param_name) or []

        # First argument: get docker compose commands dynamically
        if len(args) == 0:
            try:
                result = subprocess.run(
                    ["docker", "compose", "--help"],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0:
                    commands = []
                    in_commands_section = False
                    for line in result.stdout.splitlines():
                        if "Commands:" in line:
                            in_commands_section = True
                            continue
                        if in_commands_section:
                            stripped = line.strip()
                            if not stripped or stripped.startswith("Run "):
                                break
                            parts = stripped.split()
                            if parts:
                                commands.append(parts[0])

                    if commands:
                        return [c for c in commands if c.startswith(incomplete)]
            except Exception as e:
                logger.debug(f"Failed to get docker compose commands: {e}")

            return []

        # Second+ argument: service names from docker-compose.yml
        # Resolve {project} placeholder if project parameter provided
        file_path = compose_file_path
        if project_param_name and "{project}" in compose_file_path:
            project = ctx.params.get(project_param_name)
            if not project:
                return []
            file_path = compose_file_path.format(project=project)

        compose_file = Path(file_path)

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

    return _complete


def create_stack_command(stack_name: str, compose_dir: str, deploy_func, description: str):
    """
    Create a standardized stack management command.

    This factory function creates a Click command that:
    - Intercepts 'up' to use smart deployment
    - Forwards all other commands to docker compose
    - Provides dynamic completion

    Args:
        stack_name: Name of the stack (e.g., "dns", "proxy")
        compose_dir: Directory containing docker-compose.yml
        deploy_func: Deployment function to call for 'up' (e.g., deploy_dns_stack)
        description: Human-readable description for help text

    Returns:
        Click command function
    """
    import logging
    import subprocess
    import sys
    import click
    from lib.data import get_env_with_secrets
    from lib.version_check import check_schema_version

    logger = logging.getLogger(__name__)

    # Extract first line of description for short help (before any newlines)
    short_help = description.split('\n')[0] if description else f"{stack_name} stack management"

    # Build full help text
    full_help = f"""{description}

Forwards all commands to docker compose with automatic secret loading.
The 'up' command uses smart deployment (regenerate + pull + rollout).

Examples:
    itsup {stack_name} up                    # Smart deploy {stack_name} stack
    itsup {stack_name} down                  # Stop {stack_name} stack
    itsup {stack_name} logs -f               # Tail logs
    itsup {stack_name} restart               # Restart services
    itsup {stack_name} ps                    # List containers
"""

    @click.command(name=stack_name,
                   short_help=short_help,
                   help=full_help,
                   context_settings=dict(ignore_unknown_options=True, allow_interspersed_args=False))
    @click.argument("args", nargs=-1, type=click.UNPROCESSED,
                    shell_complete=complete_docker_compose_command(f"{compose_dir}/docker-compose.yml"))
    def stack_command(args):
        check_schema_version()

        if not args:
            click.echo(stack_command.get_help(click.Context(stack_command)))
            sys.exit(0)

        # Special case: 'up' uses smart deployment
        if args[0] == "up":
            service = args[1] if len(args) > 1 else None
            try:
                deploy_func(service=service)
            except Exception as e:
                logger.error(f"✗ Failed to deploy {stack_name} stack: {e}")
                sys.exit(1)
            return

        # All other commands: forward to docker compose
        cmd = ["docker", "compose", "-f", f"{compose_dir}/docker-compose.yml", *args]

        try:
            subprocess.run(cmd, env=get_env_with_secrets(), check=True)
        except subprocess.CalledProcessError as e:
            sys.exit(e.returncode)
        except KeyboardInterrupt:
            sys.exit(0)

    return stack_command
