#!/usr/bin/env python3

"""
itsup status command

Show git status for projects/ and secrets/ repos.
"""

import subprocess
import sys
from pathlib import Path

import click

from commands.common import ok, warn
from lib.paths import root as install_root


def _run_git_status(path: Path, name: str) -> bool:
    """Run git status in a repo directory

    Returns: True if clean, False if dirty
    """
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )

        status_output = result.stdout.strip()

        if status_output:
            click.echo(click.style(f"{name}/ repo (has changes):", fg="yellow"))
            click.echo(status_output)
            click.echo()
            return False
        else:
            click.echo(click.style(f"{name}/ repo (clean)", fg="green"))
            click.echo()
            return True

    except subprocess.CalledProcessError as e:
        warn(f"Could not check {name}/ status: {e}")
        return True


@click.command()
def status() -> None:
    """📊 Show git status for "projects" and "secrets" repos

    Check for uncommitted changes in your configuration repositories.

    \b
    Examples:
        itsup status    # Show git status for both repos
    """
    click.echo("Git Status")
    click.echo("==========")
    click.echo()

    # Get project root
    repo_root = install_root()

    # Check both repos
    projects_clean = _run_git_status(repo_root / "projects", "projects")
    secrets_clean = _run_git_status(repo_root / "secrets", "secrets")

    # Summary
    if projects_clean and secrets_clean:
        ok("All repos clean")
    else:
        warn("Repos have uncommitted changes")
        click.echo()
        click.echo("To commit changes:")
        click.echo("  itsup commit 'Your commit message'")
