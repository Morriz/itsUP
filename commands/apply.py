#!/usr/bin/env python3

"""Apply configurations (regenerate + deploy)"""

import logging
import subprocess
import sys

import click

from lib.data import list_projects
from lib.proxy import update_proxy, write_proxies

logger = logging.getLogger(__name__)


def _write_upstream(project_name: str) -> None:
    """Generate upstream/{project}/docker-compose.yml - imported from write-artifacts.py"""
    # Import here to avoid circular dependencies
    from bin.write_artifacts import write_upstream

    write_upstream(project_name)


def _write_upstreams() -> bool:
    """Generate all upstream configs - imported from write-artifacts.py"""
    # Import here to avoid circular dependencies
    from bin.write_artifacts import write_upstreams

    return write_upstreams()


@click.command()
@click.argument("project", required=False)

def apply(project):
    """
    Apply configurations (regenerate + deploy)

    Examples:
        itsup apply                  # Deploy all (regenerate + up -d)
        itsup apply instrukt-ai      # Deploy one project (smart sync + up -d)
    """
    if project:
        # Apply single project
        logger.info(f"Deploying {project}...")

        # Validate project exists
        projects = list_projects()
        if project not in projects:
            click.echo(f"Error: Project '{project}' not found", err=True)
            click.echo(f"Available: {', '.join(projects)}", err=True)
            sys.exit(1)

        # Smart sync (regenerate compose file with Traefik labels)
        logger.info(f"Syncing {project}...")
        _write_upstream(project)

        # Deploy with -d (daemonize)
        upstream_dir = f"upstream/{project}"
        compose_file = f"{upstream_dir}/docker-compose.yml"

        cmd = [
            "docker",
            "compose",
            "--project-directory",
            upstream_dir,
            "-p",
            project,
            "-f",
            compose_file,
            "up",
            "-d",
        ]

        logger.info(f"Running: {' '.join(cmd)}")

        try:
            subprocess.run(cmd, check=True)
            logger.info(f"✓ {project} deployed")
        except subprocess.CalledProcessError as e:
            logger.error(f"✗ {project} deployment failed")
            sys.exit(e.returncode)

    else:
        # Apply all
        logger.info("Deploying all projects...")

        # Regenerate proxy configs
        logger.info("Writing proxy configs...")
        write_proxies()

        # Regenerate all upstreams
        logger.info("Writing upstream configs...")
        if not _write_upstreams():
            logger.error("Failed to generate some upstream configs")
            sys.exit(1)

        # Deploy proxy
        logger.info("Updating proxy...")
        update_proxy()

        # Deploy all upstreams
        logger.info("Deploying all upstreams...")
        for proj in list_projects():
            upstream_dir = f"upstream/{proj}"
            compose_file = f"{upstream_dir}/docker-compose.yml"

            cmd = [
                "docker",
                "compose",
                "--project-directory",
                upstream_dir,
                "-p",
                proj,
                "-f",
                compose_file,
                "up",
                "-d",
            ]

            logger.info(f"Deploying {proj}...")
            try:
                subprocess.run(cmd, check=True)
                logger.info(f"  ✓ {proj}")
            except subprocess.CalledProcessError:
                logger.error(f"  ✗ {proj} failed")

        logger.info("✓ Apply complete")
