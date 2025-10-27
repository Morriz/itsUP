#!/usr/bin/env python3

"""Orchestrated shutdown of complete itsUP stack"""

import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import click

from lib.data import get_env_with_secrets, list_projects

logger = logging.getLogger(__name__)


def _stop_project(project: str) -> tuple[str, bool, str]:
    """Stop a single project. Returns (project, success, error_msg)"""
    compose_file = Path("upstream") / project / "docker-compose.yml"
    if not compose_file.exists():
        return (project, True, "No docker-compose.yml")

    env = get_env_with_secrets(project)
    try:
        subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "down"], env=env, check=True, capture_output=True, text=True
        )
        return (project, True, "")
    except subprocess.CalledProcessError as e:
        return (project, False, str(e))


@click.command()
@click.option("--clean", is_flag=True, help="Also remove stopped containers from itsUP-managed projects")
def down(clean: bool):
    """
    🛑 Stop ALL containers: DNS, proxy, AND all upstream projects

    Stops everything in reverse order (in parallel where possible):
    1. Container security monitor
    2. API server
    3. All upstream projects (IN PARALLEL)
    4. Proxy stack (Traefik + dockerproxy + CrowdSec)
    5. DNS stack

    With --clean: Also removes stopped containers from itsUP-managed projects (in parallel).
    Only touches itsUP containers - never affects other Docker containers.

    Examples:
        itsup down           # Stop everything
        itsup down --clean   # Stop + remove stopped containers
    """
    logger.info("🛑 Stopping EVERYTHING (all projects + infrastructure)...")

    # Step 1: Stop monitor
    logger.info("  🛡️  Stopping container security monitor...")
    try:
        subprocess.run(["pkill", "-f", "bin/monitor.py"], check=False)
        logger.info("  ✓ Monitor stopped")
    except subprocess.CalledProcessError:
        logger.warning("  ⚠ Monitor may not have been running")

    # Step 2: Stop API server
    logger.info("  🌐 Stopping API server...")
    try:
        subprocess.run(["pkill", "-f", "api/main.py"], check=False)
        logger.info("  ✓ API server stopped")
    except subprocess.CalledProcessError:
        logger.warning("  ⚠ API server may not have been running")

    # Step 3: Stop ALL upstream projects IN PARALLEL
    logger.info("  📦 Stopping all upstream projects (in parallel)...")
    projects = list_projects()

    with ThreadPoolExecutor(max_workers=10) as executor:
        # Submit all projects for parallel shutdown
        futures = {executor.submit(_stop_project, project): project for project in projects}

        # Collect results as they complete
        for future in as_completed(futures):
            project, success, error_msg = future.result()
            if error_msg == "No docker-compose.yml":
                logger.debug(f"    ⊘ {project}: No docker-compose.yml, skipping")
            elif success:
                logger.info(f"    ✓ {project} stopped")
            else:
                logger.warning(f"    ⚠ Failed to stop {project}: {error_msg}")

    # Step 4: Stop proxy stack
    logger.info("  🔀 Stopping proxy stack...")
    env = get_env_with_secrets()
    try:
        subprocess.run(["docker", "compose", "-f", "proxy/docker-compose.yml", "down"], env=env, check=True)
        logger.info("  ✓ Proxy stack stopped")
    except subprocess.CalledProcessError:
        logger.error("  ✗ Failed to stop proxy stack")

    # Step 5: Stop DNS stack
    logger.info("  📡 Stopping DNS stack...")
    try:
        subprocess.run(["docker", "compose", "-f", "dns/docker-compose.yml", "down"], env=env, check=True)
        logger.info("  ✓ DNS stack stopped")
    except subprocess.CalledProcessError:
        logger.error("  ✗ Failed to stop DNS stack")

    logger.info("✅ Everything stopped")

    # Step 6: Clean up if requested (only itsup-managed resources, in parallel)
    if clean:
        logger.info("")
        logger.info("🗑️  Cleaning up stopped itsUP containers (in parallel)...")

        def _cleanup_project(project: str) -> tuple[str, bool]:
            """Clean up a single project. Returns (project, success)"""
            compose_file = Path("upstream") / project / "docker-compose.yml"
            if not compose_file.exists():
                return (project, True)

            env = get_env_with_secrets(project)
            try:
                subprocess.run(
                    ["docker", "compose", "-f", str(compose_file), "rm", "-f"], env=env, check=True, capture_output=True
                )
                return (project, True)
            except subprocess.CalledProcessError:
                return (project, True)  # Already removed

        def _cleanup_stack(stack: str) -> tuple[str, bool]:
            """Clean up infrastructure stack. Returns (stack, success)"""
            env = get_env_with_secrets()
            try:
                subprocess.run(
                    ["docker", "compose", "-f", f"{stack}/docker-compose.yml", "rm", "-f"],
                    env=env,
                    check=True,
                    capture_output=True,
                )
                return (stack, True)
            except subprocess.CalledProcessError:
                return (stack, True)  # Already removed

        with ThreadPoolExecutor(max_workers=10) as executor:
            # Submit all cleanup tasks in parallel
            futures = []

            # Add project cleanups
            for project in projects:
                futures.append(executor.submit(_cleanup_project, project))

            # Add infrastructure cleanups
            for stack in ["proxy", "dns"]:
                futures.append(executor.submit(_cleanup_stack, stack))

            # Wait for all to complete
            for future in as_completed(futures):
                future.result()  # Just wait, don't log individual completions

        logger.info("  ✅ Cleanup complete")
