#!/usr/bin/env python3

"""Apply configurations (regenerate + deploy)"""

import logging
import subprocess
import sys

import click

from bin.write_artifacts import write_upstream, write_upstreams
from lib.data import list_projects
from lib.proxy import update_proxy, write_proxies

logger = logging.getLogger(__name__)


def _build_docker_compose_cmd(project: str) -> list[str]:
    """
    Build docker compose command for deploying a project.

    Args:
        project: Project name

    Returns:
        List of command arguments for docker compose up -d
    """
    upstream_dir = f"upstream/{project}"
    compose_file = f"{upstream_dir}/docker-compose.yml"
    return [
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
        write_upstream(project)

        # Deploy with -d (daemonize)
        cmd = _build_docker_compose_cmd(project)
        logger.info(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.info(f"✓ {project} deployed")
        except subprocess.CalledProcessError as e:
            logger.error(f"✗ {project} deployment failed")
            if e.stderr:
                logger.error(f"Error details: {e.stderr}")
            sys.exit(e.returncode)

    else:
        # Apply all
        logger.info("Deploying all projects...")

        # Regenerate proxy configs
        logger.info("Writing proxy configs...")
        write_proxies()

        # Regenerate all upstreams
        logger.info("Writing upstream configs...")
        if not write_upstreams():
            logger.error("Failed to generate some upstream configs")
            sys.exit(1)

        # Deploy proxy
        logger.info("Updating proxy...")
        update_proxy()

        # Deploy all upstreams
        logger.info("Deploying all upstreams...")
        failed_projects = []
        for proj in list_projects():
            cmd = _build_docker_compose_cmd(proj)

            logger.info(f"Deploying {proj}...")
            try:
                result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                logger.info(f"  ✓ {proj}")
            except subprocess.CalledProcessError as e:
                logger.error(f"  ✗ {proj} failed")
                if e.stderr:
                    logger.error(f"  Error details: {e.stderr}")
                failed_projects.append(proj)

        if failed_projects:
            logger.error(f"Failed projects: {', '.join(failed_projects)}")
            sys.exit(1)

        logger.info("✓ Apply complete")
