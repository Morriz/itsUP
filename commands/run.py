#!/usr/bin/env python3

"""Orchestrated startup of complete itsUP stack"""

import logging
import subprocess
import sys

import click

from bin.write_artifacts import write_proxy_artifacts
from lib.data import get_env_with_secrets

logger = logging.getLogger(__name__)


@click.command()
def run():
    """
    🚀 Run itsUP stack: dns, proxy and monitor (needs sudo)

    Starts all infrastructure components in the correct order:
    1. DNS stack (creates proxynet network)
    2. Proxy stack (Traefik + dockerproxy)
    3. API server (Python process)
    4. Container security monitor

    This is different from individual stack commands (dns up, proxy up)
    as it orchestrates the complete startup sequence including monitoring.

    Examples:
        itsup run    # Start everything including monitor
    """
    logger.info("🚀 Running itsUP complete stack...")

    # Step 0: Regenerate proxy artifacts (in case config changed)
    logger.info("  🔧 Regenerating proxy artifacts...")
    try:
        write_proxy_artifacts()
        logger.info("  ✓ Proxy artifacts regenerated")
    except Exception as e:
        logger.error(f"  ✗ Failed to regenerate proxy artifacts: {e}")
        sys.exit(1)

    # Get environment with infrastructure secrets (itsup.txt)
    env = get_env_with_secrets()

    # Step 1: Start DNS stack (creates network)
    logger.info("  📡 Starting DNS stack...")
    try:
        subprocess.run(["docker", "compose", "-f", "dns/docker-compose.yml", "up", "-d", "--pull", "always"], env=env, check=True)
        logger.info("  ✓ DNS stack started")
    except subprocess.CalledProcessError as e:
        logger.error("  ✗ Failed to start DNS stack")
        sys.exit(e.returncode)

    # Step 2: Start proxy stack
    logger.info("  🔀 Starting proxy stack...")
    try:
        subprocess.run(["docker", "compose", "-f", "proxy/docker-compose.yml", "up", "-d", "--pull", "always"], env=env, check=True)
        logger.info("  ✓ Proxy stack started")
    except subprocess.CalledProcessError as e:
        logger.error("  ✗ Failed to start proxy stack")
        sys.exit(e.returncode)

    # Step 3: Start API server
    logger.info("  🌐 Starting API server...")
    try:
        subprocess.run(["./bin/start-api.sh"], check=True)
        logger.info("  ✓ API server started")
    except subprocess.CalledProcessError as e:
        logger.error("  ✗ Failed to start API server")
        sys.exit(e.returncode)

    # Step 4: Start container security monitor
    logger.info("  🛡️  Starting container security monitor...")
    try:
        subprocess.run(["./bin/start-monitor.sh"], check=True)
        logger.info("  ✓ Monitor started")
    except subprocess.CalledProcessError as e:
        logger.error("  ✗ Failed to start monitor")
        sys.exit(e.returncode)

    logger.info("✅ Complete stack running")
