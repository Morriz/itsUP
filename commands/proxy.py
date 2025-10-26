#!/usr/bin/env python3

"""Proxy stack management (Traefik + dockerproxy)"""

import logging
import subprocess
import sys

import click

from bin.write_artifacts import write_proxy_artifacts
from lib.data import get_env_with_secrets

logger = logging.getLogger(__name__)

PROXY_DIR = "proxy"


@click.group()
def proxy():
    """
    🔀 Proxy stack management

    Manages the Traefik reverse proxy stack including dockerproxy.
    This stack must be started after the DNS stack.

    Examples:
        itsup proxy up        # Start proxy stack
        itsup proxy down      # Stop proxy stack
        itsup proxy logs      # Tail proxy logs
    """
    pass


@proxy.command()
@click.argument("service", required=False)
def up(service):
    """
    Start proxy stack (regenerates configs first)

    Always regenerates proxy configuration to ensure it's up to date,
    then starts containers.

    SERVICE: Optional service name (traefik, dockerproxy)

    Examples:
        itsup proxy up            # Start all proxy services
        itsup proxy up traefik    # Start only Traefik
    """
    # Always regenerate proxy artifacts (they're templates, always need refresh)
    try:
        write_proxy_artifacts()
    except Exception as e:
        logger.error(f"✗ Failed to regenerate proxy config: {e}")
        sys.exit(1)

    logger.info("Starting proxy stack...")

    cmd = ["docker", "compose", "-f", f"{PROXY_DIR}/docker-compose.yml", "up", "-d", "--pull", "always"]
    if service:
        cmd.append(service)

    try:
        subprocess.run(cmd, env=get_env_with_secrets(), check=True)
        logger.info("✓ Proxy stack started")
    except subprocess.CalledProcessError as e:
        logger.error("✗ Failed to start proxy stack")
        sys.exit(e.returncode)


@proxy.command()
@click.argument("service", required=False)
def down(service):
    """
    Stop proxy stack

    Stops Traefik and dockerproxy containers.

    SERVICE: Optional service name (traefik, dockerproxy)

    Examples:
        itsup proxy down            # Stop all proxy services
        itsup proxy down traefik    # Stop only Traefik
    """
    logger.info("Stopping proxy stack...")

    cmd = ["docker", "compose", "-f", f"{PROXY_DIR}/docker-compose.yml", "down"]
    if service:
        cmd = ["docker", "compose", "-f", f"{PROXY_DIR}/docker-compose.yml", "stop"]
        cmd.append(service)

    try:
        subprocess.run(cmd, env=get_env_with_secrets(), check=True)
        logger.info("✓ Proxy stack stopped")
    except subprocess.CalledProcessError as e:
        logger.error("✗ Failed to stop proxy stack")
        sys.exit(e.returncode)


@proxy.command()
@click.argument("service", required=False)
def restart(service):
    """
    Restart proxy stack

    Restarts Traefik and dockerproxy containers.

    SERVICE: Optional service name (traefik, dockerproxy)

    Examples:
        itsup proxy restart            # Restart all proxy services
        itsup proxy restart traefik    # Restart only Traefik
    """
    logger.info("Restarting proxy stack...")

    cmd = ["docker", "compose", "-f", f"{PROXY_DIR}/docker-compose.yml", "restart"]
    if service:
        cmd.append(service)

    try:
        subprocess.run(cmd, env=get_env_with_secrets(), check=True)
        logger.info("✓ Proxy stack restarted")
    except subprocess.CalledProcessError as e:
        logger.error("✗ Failed to restart proxy stack")
        sys.exit(e.returncode)


@proxy.command()
@click.argument("service", required=False)
def logs(service):
    """
    Tail proxy stack logs

    Shows logs for proxy services.

    SERVICE: Optional service name (traefik, dockerproxy)

    Examples:
        itsup proxy logs                # Tail all proxy logs
        itsup proxy logs traefik        # Tail Traefik logs
        itsup proxy logs dockerproxy    # Tail dockerproxy logs
    """
    cmd = ["docker", "compose", "-f", f"{PROXY_DIR}/docker-compose.yml", "logs", "-f"]
    if service:
        cmd.append(service)

    try:
        subprocess.run(cmd, env=get_env_with_secrets(), check=True)
    except subprocess.CalledProcessError as e:
        logger.error("✗ Failed to tail proxy logs")
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        logger.info("Stopped tailing logs")
        sys.exit(0)
