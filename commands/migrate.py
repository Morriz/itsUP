#!/usr/bin/env python3

"""Migration commands"""

import sys

import click

from commands.common import fail, ok
from lib.migrations import migrate


@click.command()
@click.option("--dry-run", is_flag=True, help="Show what would change without making changes")
@click.option("--list", "list_only", is_flag=True, help="Show which fixers would run")
def migrate_cmd(dry_run: bool, list_only: bool) -> None:
    """
    🔄 Migrate configuration schema to latest version

    Run all pending migrations to upgrade your configuration schema
    to match the current itsUP version.

    \b
    Examples:
        itsup migrate              # Run all pending migrations
        itsup migrate --dry-run    # Show what would change
        itsup migrate --list       # Show which fixers would run
    """
    success = migrate(dry_run=dry_run, list_only=list_only)

    if not success and not list_only:
        fail("Migration did not complete successfully; see the log for details")
        sys.exit(1)

    if success and not list_only:
        ok("Migration complete")
