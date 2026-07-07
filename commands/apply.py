#!/usr/bin/env python3

"""Apply configurations (regenerate + deploy with smart rollout)"""

import sys

import click

from commands.common import (
    complete_stack_or_project,
    fail,
    guard_schema_version,
    ok,
    step,
)
from lib.data import list_projects, list_projects_topo, validate_all
from lib.deploy import deploy_dns_stack, deploy_proxy_stack, deploy_upstream_project


@click.command()
@click.argument("project", required=False, shell_complete=complete_stack_or_project)
def apply(project: str | None) -> None:
    """
    ⚙️ Apply configurations with smart zero-downtime rollout [PROJECT]

    Regenerates docker-compose files with Traefik labels and deploys with smart rollout:

    \b
    - Stateless services: zero-downtime rollout via docker-rollout
    - Stateful services: normal restart via docker compose up -d
    - Change detection: skips rollout if config unchanged

    Handles infrastructure stacks (dns, proxy) and upstream projects.

    \b
    Examples:
        itsup apply                  # Deploy all (dns + proxy + all projects)
        itsup apply dns              # Deploy DNS stack
        itsup apply proxy            # Deploy proxy stack
        itsup apply instrukt-ai      # Deploy single project
    """
    guard_schema_version()

    # Design-by-contract gate: the whole config must hold its invariants before we
    # touch anything. Global and fail-closed — one invalid project or a cross-project
    # collision blocks every deploy until the config is valid again.
    errors = validate_all()
    if errors:
        for proj, errs in errors.items():
            for err in errs:
                click.echo(f"  {proj}: {err}", err=True)
        click.echo("Validation failed; refusing to deploy", err=True)
        sys.exit(1)

    def _deploy_single(target: str) -> tuple[str, bool, str]:
        """Deploy a single stack or project. Returns (target, success, error_msg)"""
        try:
            if target == "dns":
                deploy_dns_stack()
            elif target == "proxy":
                deploy_proxy_stack()
            else:
                deploy_upstream_project(target)
            return (target, True, "")
        except Exception as e:
            return (target, False, str(e))

    if project:
        # Apply single stack or project
        step(f"Deploying {project} with smart rollout...")

        # Validate exists (membership only — order doesn't matter here)
        valid_targets = ["dns", "proxy"] + list_projects()
        if project not in valid_targets:
            click.echo(f"Error: '{project}' not found", err=True)
            click.echo(f"Available: dns, proxy, {', '.join(list_projects())}", err=True)
            sys.exit(1)

        # Deploy
        _, success, error_msg = _deploy_single(project)
        if success:
            ok(f"{project} deployed")
        else:
            fail(f"{project} deployment failed: {error_msg}")
            sys.exit(1)

    else:
        # Apply all (dns + proxy + upstreams)
        step("Deploying all stacks with smart rollout...")

        # Deploy ALL targets sequentially (dns, proxy, and all projects)
        all_targets = ["dns", "proxy"] + list_projects_topo()
        failed = []

        for target in all_targets:
            target, success, error_msg = _deploy_single(target)
            if success:
                ok(f"  {target}")
            else:
                fail(f"  {target} failed: {error_msg}")
                failed.append(target)

        if failed:
            fail(f"Failed: {', '.join(failed)}")
            sys.exit(1)

        ok("Apply complete")
