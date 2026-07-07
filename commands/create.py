#!/usr/bin/env python3

"""itsup create command — scaffold a new project."""

import sys

import click

from commands.common import fail, guard_schema_version, ok
from lib.paths import root as install_root
from lib.projects import create_project


@click.command()
@click.argument("name")
def create(name: str) -> None:
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
    guard_schema_version()

    repo_root = install_root()

    try:
        create_project(name, repo_root)
    except ValueError as e:
        fail(str(e))
        sys.exit(1)

    click.echo()
    ok(f"Project '{name}' created successfully!")
    click.echo("Next steps:")
    click.echo(f"  1. Edit config:  projects/{name}/itsup-project.yml")
    click.echo(f"  2. Edit compose: projects/{name}/docker-compose.yml")
    click.echo(f"  3. Add secrets:  secrets/{name}.txt")
    click.echo(f"  4. Deploy:       itsup apply {name}")
