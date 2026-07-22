#!/usr/bin/env python3

"""itsup pull command — pull changes from projects and secrets repos."""

import subprocess
import sys

import click

from commands.common import fail, guard_schema_version, ok
from lib.paths import root as install_root
from lib.sync import pull_repos


@click.command()
@click.option("--apply", "-a", "run_apply", is_flag=True, help="Run 'itsup apply' after successful pull")
def pull(run_apply: bool) -> None:
    """Pull changes from "projects" and "secrets" repos

    Updates local configuration from remote repositories.
    Uses 'git pull --rebase' to preserve local history.

    \b
    Examples:
        itsup pull
        itsup pull --apply
    """
    guard_schema_version()

    repo_root = install_root()

    click.echo("Pulling changes...")
    results = pull_repos(repo_root)

    for repo, success in results.items():
        if success:
            ok(f"{repo}/ updated")
        else:
            fail(f"{repo}/ failed")

    if not all(results.values()):
        click.echo()
        fail("Some updates failed. Fix conflicts manually.")
        sys.exit(1)

    click.echo()
    ok("All repos updated")

    if run_apply:
        click.echo()
        click.echo("Running apply...")
        try:
            subprocess.run([str(repo_root / ".venv" / "bin" / "itsup"), "apply"], check=True)
        except subprocess.CalledProcessError:
            sys.exit(1)
