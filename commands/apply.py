#!/usr/bin/env python3

"""Apply configurations (regenerate + deploy)"""

import logging
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import click

from bin.write_artifacts import write_upstream, write_upstreams
from lib.data import get_env_with_secrets, list_projects

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
        "--pull",
        "always",
    ]


@click.command()
@click.argument("project", required=False)
def apply(project):
    """
    ⚙️ Apply configurations to upstream projects [PROJECT] (regenerate + deploy)

    Regenerates docker-compose files with Traefik labels and deploys projects.
    Does NOT touch DNS or proxy stacks - only upstream projects.

    Examples:
        itsup apply                  # Deploy all projects (in parallel)
        itsup apply instrukt-ai      # Deploy single project
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
            subprocess.run(cmd, env=get_env_with_secrets(project), check=True)
            logger.info(f"✓ {project} deployed")
        except subprocess.CalledProcessError as e:
            logger.error(f"✗ {project} deployment failed")
            sys.exit(e.returncode)

    else:
        # Apply all
        logger.info("Deploying all projects...")

        # Regenerate all upstreams
        logger.info("Writing upstream configs...")
        if not write_upstreams():
            logger.error("Failed to generate some upstream configs")
            sys.exit(1)

        # Deploy all upstreams IN PARALLEL
        logger.info("Deploying all upstreams (in parallel)...")

        def _deploy_project(proj: str) -> tuple[str, bool, str]:
            """Deploy a single project. Returns (project, success, error_msg)"""
            cmd = _build_docker_compose_cmd(proj)
            try:
                subprocess.run(
                    cmd,
                    env=get_env_with_secrets(proj),
                    check=True,
                    capture_output=True,
                    text=True
                )
                return (proj, True, "")
            except subprocess.CalledProcessError as e:
                return (proj, False, e.stderr if e.stderr else str(e))

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
