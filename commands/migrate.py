#!/usr/bin/env python3

"""Migration commands"""

import logging
import sys

import click

from lib.migrations import migrate

logger = logging.getLogger(__name__)


@click.command()
@click.option("--dry-run", is_flag=True, help="Show what would change without making changes")
@click.option("--list", "list_only", is_flag=True, help="Show which fixers would run")
def migrate_cmd(dry_run, list_only):
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
        sys.exit(1)
