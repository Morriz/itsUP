#!/usr/bin/env python3

"""
itsup projects command

Discover configured projects and the files that constitute them.
"""

import sys

import click

from commands.common import complete_project, display_path, fail
from lib.data import list_projects
from lib.paths import root as install_root


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
    repo_root = install_root()
    configured = list_projects()

    if name is None:
        for project_name in sorted(configured):
            click.echo(project_name)
        return

    if name not in configured:
        fail(f"Unknown project: {name}")
        sys.exit(1)

    project_dir = repo_root / "projects" / name
    for file_path in sorted(p for p in project_dir.rglob("*") if p.is_file()):
        click.echo(display_path(file_path))

    secrets_dir = repo_root / "secrets"
    for suffix in (".enc.txt", ".txt"):
        secret_path = secrets_dir / f"{name}{suffix}"
        if secret_path.exists():
            click.echo(display_path(secret_path))
