#!/usr/bin/env python3

"""
itsup projects command

Discover configured projects and the files that constitute them.
"""

import sys

import click

from commands.common import complete_project, fail
from lib.data import list_projects
from lib.paths import display_path, project_dir, secret_file


@click.command()
@click.argument("name", required=False, shell_complete=complete_project)
def projects(name: str | None) -> None:
    """📋 Discover configured projects, or list NAME's files [NAME]

    Read-only discovery for agent GitOps workflows — never gated host-only.

    \b
    Without NAME: prints the configured project names, one per line.
    With NAME: prints every file that constitutes that project — its files
    under projects/<name>/ and its secret file(s) under secrets/ — one
    location per line, usable from the caller's cwd.

    \b
    Examples:
        itsup projects               # List configured project names
        itsup projects my-project    # List my-project's files
    """
    configured = list_projects()

    if name is None:
        for project_name in sorted(configured):
            click.echo(project_name)
        return

    if name not in configured:
        fail(f"Unknown project: {name}")
        sys.exit(1)

    for file_path in sorted(p for p in project_dir(name).rglob("*") if p.is_file()):
        click.echo(display_path(file_path))

    for encrypted in (True, False):
        secret_path = secret_file(name, encrypted=encrypted)
        if secret_path.exists():
            click.echo(display_path(secret_path))
