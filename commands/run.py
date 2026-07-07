#!/usr/bin/env python3

"""Orchestrated startup of complete itsUP stack"""

import subprocess
import sys

import click

from bin.write_artifacts import write_proxy_artifacts
from commands.common import fail, guard_schema_version, ok, step
from lib.data import get_env_with_secrets
from lib.paths import root


@click.command()
def run() -> None:
    """
    🚀 Run itsUP stack: dns, proxy and monitor (needs sudo)

    Starts all infrastructure components in the correct order:

    \b
    1. DNS stack (creates proxynet network)
    2. Proxy stack (Traefik + dockerproxy)
    3. API server (Python process)
    4. Container security monitor (report-only mode)

    This is different from individual stack commands (dns up, proxy up)
    as it orchestrates the complete startup sequence including monitoring.

    The monitor runs in report-only mode (detection without blocking).
    For full protection, use: itsup monitor start

    \b
    Examples:
        itsup run    # Start everything including monitor (report-only)
    """
    guard_schema_version()
    step("🚀 Running itsUP complete stack...")

    # Step 0: Regenerate proxy artifacts (in case config changed)
    step("  🔧 Regenerating proxy artifacts...")
    try:
        write_proxy_artifacts()
        ok("  Proxy artifacts regenerated")
    except Exception as e:
        fail(f"  Failed to regenerate proxy artifacts: {e}")
        sys.exit(1)

    # Get environment with infrastructure secrets (itsup.txt)
    env = get_env_with_secrets()

    # Step 1: Start DNS stack (creates network)
    step("  📡 Starting DNS stack...")
    try:
        # No --pull at boot: the Pi's own DNS may not be working yet (chicken-and-egg
        # with AdGuard). Use cached images. Pulls happen via itsup-apply.timer / manual apply.
        subprocess.run(
            ["docker", "compose", "-f", str(root() / "dns" / "docker-compose.yml"), "up", "-d"], env=env, check=True
        )
        ok("  DNS stack started")
    except subprocess.CalledProcessError as e:
        fail("  Failed to start DNS stack")
        sys.exit(e.returncode)

    # Step 2: Start proxy stack
    step("  🔀 Starting proxy stack...")
    try:
        subprocess.run(
            ["docker", "compose", "-f", str(root() / "proxy" / "docker-compose.yml"), "up", "-d"], env=env, check=True
        )
        ok("  Proxy stack started")
    except subprocess.CalledProcessError as e:
        fail("  Failed to start proxy stack")
        sys.exit(e.returncode)

    # Step 3: Start API server
    step("  🌐 Starting API server...")
    try:
        subprocess.run([str(root() / "bin" / "start-api.sh")], check=True)
        ok("  API server started")
    except subprocess.CalledProcessError as e:
        fail("  Failed to start API server")
        sys.exit(e.returncode)

    # Step 4: Start container security monitor (report-only mode)
    step("  🛡️  Starting container security monitor (report-only mode)...")
    try:
        subprocess.run([str(root() / "bin" / "start-monitor.sh"), "--report-only"], check=True)
        ok("  Monitor started in report-only mode")
    except subprocess.CalledProcessError as e:
        fail("  Failed to start monitor")
        sys.exit(e.returncode)

    ok("Complete stack running")
