#!/usr/bin/env python3

"""Apply configurations (regenerate + deploy with smart rollout)"""

import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import click

from lib.data import list_projects
from lib.deploy import deploy_upstream_project

logger = logging.getLogger(__name__)


@click.command()
@click.argument("project", required=False)
def apply(project):
    """
    ⚙️ Apply configurations with smart zero-downtime rollout [PROJECT]

    Regenerates docker-compose files with Traefik labels and deploys with smart rollout:
    - Stateless services: zero-downtime rollout via docker-rollout
    - Stateful services: normal restart via docker compose up -d
    - Change detection: skips rollout if config unchanged

    Does NOT touch DNS or proxy stacks - only upstream projects.

    Examples:
        itsup apply                  # Deploy all projects (in parallel)
        itsup apply instrukt-ai      # Deploy single project
    """
    if project:
        # Apply single project
        logger.info(f"Deploying {project} with smart rollout...")

        # Validate project exists
        projects = list_projects()
        if project not in projects:
            click.echo(f"Error: Project '{project}' not found", err=True)
            click.echo(f"Available: {', '.join(projects)}", err=True)
            sys.exit(1)

        # Deploy with smart rollout
        try:
            deploy_upstream_project(project)
            logger.info(f"✓ {project} deployed")
        except Exception as e:
            logger.error(f"✗ {project} deployment failed: {e}")
            sys.exit(1)

    else:
        # Apply all
        logger.info("Deploying all projects with smart rollout...")

        # Deploy all upstreams IN PARALLEL
        logger.info("Deploying all upstreams (in parallel)...")

        def _deploy_project(proj: str) -> tuple[str, bool, str]:
            """Deploy a single project with smart rollout. Returns (project, success, error_msg)"""
            try:
                deploy_upstream_project(proj)
                return (proj, True, "")
            except Exception as e:
                return (proj, False, str(e))

        failed_projects = []
        projects = list_projects()

        with ThreadPoolExecutor(max_workers=10) as executor:
            # Submit all deployments in parallel
            futures = {executor.submit(_deploy_project, proj): proj for proj in projects}

            # Collect results as they complete
            for future in as_completed(futures):
                proj, success, error_msg = future.result()
                if success:
                    logger.info(f"  ✓ {proj}")
                else:
                    logger.error(f"  ✗ {proj} failed: {error_msg}")
                    failed_projects.append(proj)

        if failed_projects:
            logger.error(f"Failed projects: {', '.join(failed_projects)}")
            sys.exit(1)

        logger.info("✓ Apply complete")
