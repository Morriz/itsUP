#!/usr/bin/env python3

"""Container security monitor management"""

import subprocess
import sys

import click

from commands.common import fail, ok, step
from lib import supervisor
from lib.paths import root
from lib.supervisor import Unit


def _require_supervision() -> None:
    if not supervisor.supports(Unit.MONITOR):
        fail("The container security monitor is supported on Linux only")
        raise SystemExit(1)


@click.group()
def monitor() -> None:
    """
    🛡️ Container security monitor management

    Manage the container security monitor that detects compromised containers
    through DNS correlation analysis.

    \b
    Examples:
        itsup monitor start               # Start with blocking
        itsup monitor start --report-only # Detection only
        itsup monitor stop                # Stop monitor
    """
    pass


@monitor.command()
@click.option("--skip-sync", is_flag=True, help="Skip initial blacklist/whitelist sync")
@click.option("--report-only", is_flag=True, help="Detection only, no blocking")
@click.option("--use-opensnitch", is_flag=True, help="Cross-reference with OpenSnitch database")
def start(skip_sync: bool, report_only: bool, use_opensnitch: bool) -> None:
    """
    Start container security monitor

    Starts the monitor with optional configuration flags.

    \b
    Examples:
        itsup monitor start                           # Full protection mode
        itsup monitor start --report-only             # Detection only
        itsup monitor start --use-opensnitch          # With OpenSnitch integration
        itsup monitor start --skip-sync --report-only # Quick start, no blocking
    """
    flags: list[str] = []
    if skip_sync:
        flags.append("--skip-sync")
    if report_only:
        flags.append("--report-only")
    if use_opensnitch:
        flags.append("--use-opensnitch")

    flags_str = " ".join(flags)
    step(f"Starting container security monitor{' with flags: ' + flags_str if flags else ''}...")
    _require_supervision()

    try:
        supervisor.write_monitor_flags(flags)
        supervisor.restart(Unit.MONITOR)
        ok("Monitor started")
    except subprocess.CalledProcessError as e:
        fail("Failed to start monitor")
        sys.exit(e.returncode)


@monitor.command()
def stop() -> None:
    """
    Stop container security monitor

    Stops the running monitor process.

    \b
    Examples:
        itsup monitor stop
    """
    step("Stopping container security monitor...")
    _require_supervision()

    try:
        supervisor.stop(Unit.MONITOR)
        ok("Monitor stopped")
    except subprocess.CalledProcessError as e:
        fail("Failed to stop monitor")
        sys.exit(e.returncode)


@monitor.command()
def cleanup() -> None:
    """
    Review and cleanup blacklist

    Run interactive cleanup mode to review blacklisted IPs.

    \b
    Examples:
        itsup monitor cleanup
    """
    step("Running cleanup mode...")

    try:
        subprocess.run(["sudo", "python3", str(root() / "bin" / "monitor.py"), "--cleanup"], check=True)
    except subprocess.CalledProcessError as e:
        fail("Failed to run cleanup")
        sys.exit(e.returncode)


@monitor.command(name="clear-iptables")
def clear_iptables() -> None:
    """
    Clear iptables rules created by monitor

    Removes LOG and DROP rules added by the monitor without touching blacklist files.

    \b
    Examples:
        itsup monitor clear-iptables
    """
    step("Clearing iptables rules created by monitor...")

    try:
        subprocess.run(["sudo", "python3", str(root() / "bin" / "monitor.py"), "--clear-iptables"], check=True)
    except subprocess.CalledProcessError as e:
        fail("Failed to clear iptables rules")
        sys.exit(e.returncode)


@monitor.command()
def report() -> None:
    """
    Generate threat intelligence report

    Analyzes threat actors and generates a detailed report.

    \b
    Examples:
        itsup monitor report
    """
    step("Generating threat intelligence report...")

    try:
        subprocess.run(["python3", str(root() / "bin" / "analyze_threats.py")], check=True)
    except subprocess.CalledProcessError as e:
        fail("Failed to generate report")
        sys.exit(e.returncode)
