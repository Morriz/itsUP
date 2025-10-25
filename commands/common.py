#!/usr/bin/env python3

"""Common utilities for CLI commands"""

from lib.data import list_projects


def complete_project(ctx, param, incomplete):
    """
    Autocomplete project names.

    Args:
        ctx: Click context
        param: Click parameter
        incomplete: Partially typed string to complete

    Returns:
        List of project names matching the incomplete string
    """
    return [p for p in list_projects() if p.startswith(incomplete)]
