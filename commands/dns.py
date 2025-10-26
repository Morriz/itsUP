#!/usr/bin/env python3

"""DNS stack management (dns-honeypot)"""

import logging
import subprocess
import sys

import click

from lib.data import get_env_with_secrets

logger = logging.getLogger(__name__)

DNS_DIR = "dns"


@click.group()
def dns():
    """
    📡 DNS stack management

    Manages the DNS honeypot stack that logs all container DNS queries.
    This stack MUST be started first as it creates the proxynet network.

    Examples:
        itsup dns up        # Start DNS stack
        itsup dns down      # Stop DNS stack
        itsup dns logs      # Tail DNS logs
    """
    pass


@dns.command()
@click.argument("service", required=False)
def up(service):
    """
    Start DNS stack

    Starts the DNS honeypot container. This creates the proxynet network
    that other stacks will join.

    SERVICE: Optional service name to start only that service

    Examples:
        itsup dns up                # Start all DNS services
        itsup dns up dns-honeypot   # Start specific service
    """
    logger.info("Starting DNS stack...")

    cmd = ["docker", "compose", "-f", f"{DNS_DIR}/docker-compose.yml", "up", "-d", "--pull", "always"]
    if service:
        cmd.append(service)

    try:
        subprocess.run(cmd, env=get_env_with_secrets(), check=True)
        logger.info("✓ DNS stack started")
    except subprocess.CalledProcessError as e:
        logger.error("✗ Failed to start DNS stack")
        sys.exit(e.returncode)


@dns.command()
@click.argument("service", required=False)
def down(service):
    """
    Stop DNS stack

    Stops the DNS honeypot container.

    SERVICE: Optional service name to stop only that service

    Examples:
        itsup dns down                # Stop all DNS services
        itsup dns down dns-honeypot   # Stop specific service
    """
    logger.info("Stopping DNS stack...")

    cmd = ["docker", "compose", "-f", f"{DNS_DIR}/docker-compose.yml", "down"]
    if service:
        cmd = ["docker", "compose", "-f", f"{DNS_DIR}/docker-compose.yml", "stop"]
        cmd.append(service)

    try:
        subprocess.run(cmd, env=get_env_with_secrets(), check=True)
        logger.info("✓ DNS stack stopped")
    except subprocess.CalledProcessError as e:
        logger.error("✗ Failed to stop DNS stack")
        sys.exit(e.returncode)


@dns.command()
@click.argument("service", required=False)
def restart(service):
    """
    Restart DNS stack

    Restarts the DNS honeypot container.

    SERVICE: Optional service name to restart only that service

    Examples:
        itsup dns restart                # Restart all DNS services
        itsup dns restart dns-honeypot   # Restart specific service
    """
    logger.info("Restarting DNS stack...")

    cmd = ["docker", "compose", "-f", f"{DNS_DIR}/docker-compose.yml", "restart"]
    if service:
        cmd.append(service)

    try:
        subprocess.run(cmd, env=get_env_with_secrets(), check=True)
        logger.info("✓ DNS stack restarted")
    except subprocess.CalledProcessError as e:
        logger.error("✗ Failed to restart DNS stack")
        sys.exit(e.returncode)


@dns.command()
@click.argument("service", required=False)
def logs(service):
    """
    Tail DNS stack logs

    Shows logs for DNS services.

    SERVICE: Optional service name to show logs for only that service

    Examples:
        itsup dns logs                # Tail all DNS logs
        itsup dns logs dns-honeypot   # Tail specific service logs
    """
    cmd = ["docker", "compose", "-f", f"{DNS_DIR}/docker-compose.yml", "logs", "-f"]
    if service:
        cmd.append(service)

    try:
        subprocess.run(cmd, env=get_env_with_secrets(), check=True)
    except subprocess.CalledProcessError as e:
        logger.error("✗ Failed to tail DNS logs")
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        logger.info("Stopped tailing logs")
        sys.exit(0)
