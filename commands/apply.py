#!/usr/bin/env python3

"""Apply configurations (regenerate + deploy with smart rollout)"""

import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import click

from commands.common import complete_stack_or_project
from lib.data import list_projects
from lib.deploy import deploy_dns_stack, deploy_proxy_stack, deploy_upstream_project
from lib.version_check import check_schema_version

logger = logging.getLogger(__name__)


@click.command()
@click.argument("project", required=False, shell_complete=complete_stack_or_project)
def apply(project):
    """
    ⚙️ Apply configurations with smart zero-downtime rollout [PROJECT]

    Regenerates docker-compose files with Traefik labels and deploys with smart rollout:
    - Stateless services: zero-downtime rollout via docker-rollout
    - Stateful services: normal restart via docker compose up -d
    - Change detection: skips rollout if config unchanged

    Handles infrastructure stacks (dns, proxy) and upstream projects.

    Examples:
        itsup apply                  # Deploy all (dns + proxy + all projects)
        itsup apply dns              # Deploy DNS stack
        itsup apply proxy            # Deploy proxy stack
        itsup apply instrukt-ai      # Deploy single project
    """
    check_schema_version()

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
        logger.info(f"Deploying {project} with smart rollout...")

        # Validate exists
        valid_targets = ["dns", "proxy"] + list_projects()
        if project not in valid_targets:
            click.echo(f"Error: '{project}' not found", err=True)
            click.echo(f"Available: dns, proxy, {', '.join(list_projects())}", err=True)
            sys.exit(1)

        # Deploy
        _, success, error_msg = _deploy_single(project)
        if success:
            logger.info(f"✓ {project} deployed")
        else:
            logger.error(f"✗ {project} deployment failed: {error_msg}")
            sys.exit(1)

    else:
        # Apply all (dns + proxy + upstreams)
        logger.info("Deploying all stacks with smart rollout...")

        # Deploy ALL targets IN PARALLEL (dns, proxy, and all projects)
        all_targets = ["dns", "proxy"] + list_projects()
        failed = []

        with ThreadPoolExecutor(max_workers=10) as executor:
            # Submit all deployments in parallel
            futures = {executor.submit(_deploy_single, target): target for target in all_targets}

            # Collect results as they complete
            for future in as_completed(futures):
                target, success, error_msg = future.result()
                if success:
                    logger.info(f"  ✓ {target}")
                else:
                    logger.error(f"  ✗ {target} failed: {error_msg}")
                    failed.append(target)

        if failed:
            logger.error(f"Failed: {', '.join(failed)}")
            sys.exit(1)

        logger.info("✓ Apply complete")
