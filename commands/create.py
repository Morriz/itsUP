#!/usr/bin/env python3

"""itsup create command — scaffold a new project."""

import sys
from pathlib import Path

import click

from lib.projects import create_project
from lib.version_check import check_schema_version


class Colors:
    """ANSI color codes for terminal output"""

    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    NC = "\033[0m"


@click.command()
@click.argument("name")
def create(name):
    """Create a new project scaffold

    Creates a new project directory in projects/ with:
    - itsup-project.yml (routing config)
    - docker-compose.yml (service config)
    - secrets/<name>.txt (empty secrets file)

    \b
    Examples:
        itsup create my-app
        itsup create redis-cache
    """
    check_schema_version()

    root = Path(__file__).resolve().parent.parent

    try:
        create_project(name, root)
    except ValueError as e:
        click.echo(f"{Colors.RED}✗ {e}{Colors.NC}", err=True)
        sys.exit(1)

    click.echo()
    click.echo(f"{Colors.GREEN}✓ Project '{name}' created successfully!{Colors.NC}")
    click.echo("Next steps:")
    click.echo(f"  1. Edit config:  projects/{name}/itsup-project.yml")
    click.echo(f"  2. Edit compose: projects/{name}/docker-compose.yml")
    click.echo(f"  3. Add secrets:  secrets/{name}.txt")
    click.echo(f"  4. Deploy:       itsup apply {name}")
