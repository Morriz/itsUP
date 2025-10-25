#!/usr/bin/env python3

"""Validation commands"""

import logging
import sys

import click

from commands.common import complete_project
from lib.data import validate_all, validate_project

logger = logging.getLogger(__name__)


@click.command()
@click.argument("project", required=False, autocompletion=complete_project)
def validate(project):
    """
    Validate project configurations

    Examples:
        itsup validate              # Validate all projects
        itsup validate instrukt-ai  # Validate single project
    """
    if project:
        # Validate single project
        errors = validate_project(project)
        if errors:
            click.echo(f"✗ {project}: {len(errors)} error(s)", err=True)
            for error in errors:
                click.echo(f"  - {error}", err=True)
            sys.exit(1)
        else:
            click.echo(f"✓ {project}: valid")
    else:
        # Validate all projects
        all_errors = validate_all()
        if all_errors:
            click.echo(f"✗ {len(all_errors)} project(s) with errors:", err=True)
            for proj, errors in all_errors.items():
                click.echo(f"\n{proj}:", err=True)
                for error in errors:
                    click.echo(f"  - {error}", err=True)
            sys.exit(1)
        else:
            click.echo("✓ All projects valid")
