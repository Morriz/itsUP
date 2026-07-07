#!/usr/bin/env python3

"""Orchestrated shutdown of complete itsUP stack"""

import subprocess
from concurrent.futures import Future, ThreadPoolExecutor, as_completed

import click
from instrukt_ai_logging import get_logger

from commands.common import fail, ok, step, warn
from lib.data import get_env_with_secrets, list_projects
from lib.paths import root

logger = get_logger(f"itsup.{__name__}")


def _stop_project(project: str) -> tuple[str, bool, str]:
    """Stop a single project. Returns (project, success, error_msg)"""
    compose_file = root() / "upstream" / project / "docker-compose.yml"
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
def down(clean: bool) -> None:
    """
    🛑 Stop ALL containers: DNS, proxy, AND all upstream projects

    Stops everything in reverse order (in parallel where possible):

    \b
    1. Container security monitor
    2. API server
    3. All upstream projects (IN PARALLEL)
    4. Proxy stack (Traefik + dockerproxy + CrowdSec)
    5. DNS stack

    With --clean: Also removes stopped containers from itsUP-managed projects (in parallel).
    Only touches itsUP containers - never affects other Docker containers.

    \b
    Examples:
        itsup down           # Stop everything
        itsup down --clean   # Stop + remove stopped containers
    """
    step("🛑 Stopping EVERYTHING (all projects + infrastructure)...")

    # Step 1: Stop monitor
    step("  🛡️  Stopping container security monitor...")
    try:
        subprocess.run(["pkill", "-f", "bin/monitor.py"], check=False)
        ok("  Monitor stopped")
    except subprocess.CalledProcessError:
        warn("  Monitor may not have been running")

    # Step 2: Stop API server
    step("  🌐 Stopping API server...")
    try:
        subprocess.run(["pkill", "-f", "api/main.py"], check=False)
        ok("  API server stopped")
    except subprocess.CalledProcessError:
        warn("  API server may not have been running")

    # Step 3: Stop ALL upstream projects IN PARALLEL
    step("  📦 Stopping all upstream projects (in parallel)...")
    projects = list_projects()

    with ThreadPoolExecutor(max_workers=10) as executor:
        # Submit all projects for parallel shutdown
        futures = {executor.submit(_stop_project, project): project for project in projects}

        # Collect results as they complete
        for future in as_completed(futures):
            project, success, error_msg = future.result()
            if error_msg == "No docker-compose.yml":
                logger.debug("%s: No docker-compose.yml, skipping", project)
            elif success:
                ok(f"    {project} stopped")
            else:
                warn(f"    Failed to stop {project}: {error_msg}")

    # Step 4: Stop proxy stack
    step("  🔀 Stopping proxy stack...")
    env = get_env_with_secrets()
    try:
        subprocess.run(
            ["docker", "compose", "-f", str(root() / "proxy" / "docker-compose.yml"), "down"], env=env, check=True
        )
        ok("  Proxy stack stopped")
    except subprocess.CalledProcessError:
        fail("  Failed to stop proxy stack")

    # Step 5: Stop DNS stack
    step("  📡 Stopping DNS stack...")
    try:
        subprocess.run(
            ["docker", "compose", "-f", str(root() / "dns" / "docker-compose.yml"), "down"], env=env, check=True
        )
        ok("  DNS stack stopped")
    except subprocess.CalledProcessError:
        fail("  Failed to stop DNS stack")

    ok("Everything stopped")

    # Step 6: Clean up if requested (only itsup-managed resources, in parallel)
    if clean:
        click.echo()
        step("🗑️  Cleaning up stopped itsUP containers (in parallel)...")

        def _cleanup_project(project: str) -> tuple[str, bool]:
            """Clean up a single project. Returns (project, success)"""
            compose_file = root() / "upstream" / project / "docker-compose.yml"
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
                    ["docker", "compose", "-f", str(root() / stack / "docker-compose.yml"), "rm", "-f"],
                    env=env,
                    check=True,
                    capture_output=True,
                )
                return (stack, True)
            except subprocess.CalledProcessError:
                return (stack, True)  # Already removed

        with ThreadPoolExecutor(max_workers=10) as executor:
            # Submit all cleanup tasks in parallel
            cleanup_futures: list[Future[tuple[str, bool]]] = []

            # Add project cleanups
            for project in projects:
                cleanup_futures.append(executor.submit(_cleanup_project, project))

            # Add infrastructure cleanups
            for stack in ["proxy", "dns"]:
                cleanup_futures.append(executor.submit(_cleanup_stack, stack))

            # Wait for all to complete
            for cleanup_future in as_completed(cleanup_futures):
                cleanup_future.result()  # Just wait, don't log individual completions

        ok("  Cleanup complete")
