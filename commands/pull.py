#!/usr/bin/env python3

"""itsup pull command — pull changes from projects and secrets repos."""

import subprocess
import sys
from pathlib import Path

import click

from lib.sync import pull_repos
from lib.version_check import check_schema_version


class Colors:
    """ANSI color codes for terminal output"""

    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    NC = "\033[0m"


@click.command()
@click.option("--apply", "-a", "run_apply", is_flag=True, help="Run 'itsup apply' after successful pull")
def pull(run_apply):
    """Pull changes from "projects" and "secrets" repos

    Updates local configuration from remote repositories.
    Uses 'git pull --rebase' to preserve local history.

    \b
    Examples:
        itsup pull
        itsup pull --apply
    """
    check_schema_version()

    root = Path(__file__).resolve().parent.parent

    click.echo("Pulling changes...")
    results = pull_repos(root)

    for repo, ok in results.items():
        if ok:
            click.echo(f"{Colors.GREEN}✓{Colors.NC} {repo}/ updated")
        else:
            click.echo(f"{Colors.RED}✗{Colors.NC} {repo}/ failed", err=True)

    if not all(results.values()):
        click.echo()
        click.echo(f"{Colors.RED}✗ Some updates failed. Fix conflicts manually.{Colors.NC}", err=True)
        sys.exit(1)

    click.echo()
    click.echo(f"{Colors.GREEN}✓ All repos updated{Colors.NC}")

    if run_apply:
        click.echo()
        click.echo("Running apply...")
        try:
            subprocess.run([str(root / "bin" / "itsup"), "apply"], check=True)
        except subprocess.CalledProcessError:
            sys.exit(1)
