#!/usr/bin/env python3

"""itsup create command — scaffold a new project."""

import sys

import click

from commands.common import fail, guard_schema_version, ok
from lib.paths import display_path, project_dir, root, secret_file
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

    try:
        create_project(name, root())
    except ValueError as e:
        fail(str(e))
        sys.exit(1)

    created = project_dir(name)
    click.echo()
    ok(f"Project '{name}' created successfully!")
    click.echo("Next steps:")
    click.echo(f"  1. Edit config:  {display_path(created / 'itsup-project.yml')}")
    click.echo(f"  2. Edit compose: {display_path(created / 'docker-compose.yml')}")
    click.echo(f"  3. Add secrets:  {display_path(secret_file(name, encrypted=False))}")
    click.echo(f"  4. Deploy:       itsup apply {name}")
