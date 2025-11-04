#!/usr/bin/env python3

"""
itsup status command

Show git status for projects/ and secrets/ repos.
"""

import subprocess
import sys
from pathlib import Path

import click


class Colors:
    """ANSI color codes for terminal output"""

    BLUE = "\033[0;34m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    NC = "\033[0m"  # No Color


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
            click.echo(f"{Colors.YELLOW}{name}/ repo (has changes):{Colors.NC}")
            click.echo(status_output)
            click.echo()
            return False
        else:
            click.echo(f"{Colors.GREEN}{name}/ repo (clean){Colors.NC}")
            click.echo()
            return True

    except subprocess.CalledProcessError as e:
        click.echo(f"{Colors.YELLOW}⚠{Colors.NC} Could not check {name}/ status: {e}", err=True)
        return True


@click.command()
def status():
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
    root = Path(__file__).resolve().parent.parent

    # Check both repos
    projects_clean = _run_git_status(root / "projects", "projects")
    secrets_clean = _run_git_status(root / "secrets", "secrets")

    # Summary
    if projects_clean and secrets_clean:
        click.echo(f"{Colors.GREEN}✓{Colors.NC} All repos clean")
    else:
        click.echo(f"{Colors.YELLOW}⚠{Colors.NC} Repos have uncommitted changes")
        click.echo()
        click.echo("To commit changes:")
        click.echo("  itsup commit 'Your commit message'")
