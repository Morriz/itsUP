#!/usr/bin/env python3

"""Container security monitor management"""

import logging
import subprocess
import sys

import click

logger = logging.getLogger(__name__)


@click.group()
def monitor():
    """
    🛡️ Container security monitor management

    Manage the container security monitor that detects compromised containers
    through DNS correlation analysis.

    Examples:
        itsup monitor start              # Start with blocking
        itsup monitor start --report-only  # Detection only
        itsup monitor stop               # Stop monitor
        itsup monitor logs               # View logs
    """
    pass


@monitor.command()
@click.option("--skip-sync", is_flag=True, help="Skip initial blacklist/whitelist sync")
@click.option("--report-only", is_flag=True, help="Detection only, no blocking")
@click.option("--use-opensnitch", is_flag=True, help="Cross-reference with OpenSnitch database")
def start(skip_sync, report_only, use_opensnitch):
    """
    Start container security monitor

    Starts the monitor with optional configuration flags.

    Examples:
        itsup monitor start                           # Full protection mode
        itsup monitor start --report-only             # Detection only
        itsup monitor start --use-opensnitch          # With OpenSnitch integration
        itsup monitor start --skip-sync --report-only # Quick start, no blocking
    """
    flags = []
    if skip_sync:
        flags.append("--skip-sync")
    if report_only:
        flags.append("--report-only")
    if use_opensnitch:
        flags.append("--use-opensnitch")

    flags_str = " ".join(flags)
    logger.info(f"Starting container security monitor{' with flags: ' + flags_str if flags else ''}...")

    try:
        env = {"FLAGS": flags_str} if flags else {}
        subprocess.run(["./bin/start-monitor.sh"], env={**subprocess.os.environ, **env}, check=True)
    except subprocess.CalledProcessError as e:
        logger.error("Failed to start monitor")
        sys.exit(e.returncode)


@monitor.command()
def stop():
    """
    Stop container security monitor

    Stops the running monitor process.

    Examples:
        itsup monitor stop
    """
    logger.info("Stopping container security monitor...")

    try:
        subprocess.run(["sudo", "pkill", "-f", "docker_monitor.py"], check=True)
        logger.info("Monitor stopped")
    except subprocess.CalledProcessError as e:
        if e.returncode == 1:
            # pkill returns 1 if no process found
            logger.info("Monitor is not running")
        else:
            logger.error("Failed to stop monitor")
            sys.exit(e.returncode)


@monitor.command()
def logs():
    """
    Tail monitor logs

    Shows real-time monitor logs.

    Examples:
        itsup monitor logs
    """
    try:
        subprocess.run(["tail", "-f", "logs/monitor.log"], check=True)
    except subprocess.CalledProcessError as e:
        logger.error("Failed to tail monitor logs")
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        logger.info("Stopped tailing logs")
        sys.exit(0)


@monitor.command()
def cleanup():
    """
    Review and cleanup blacklist

    Run interactive cleanup mode to review blacklisted IPs.

    Examples:
        itsup monitor cleanup
    """
    logger.info("Running cleanup mode...")

    try:
        subprocess.run(["sudo", "python3", "bin/monitor.py", "--cleanup"], check=True)
    except subprocess.CalledProcessError as e:
        logger.error("Failed to run cleanup")
        sys.exit(e.returncode)


@monitor.command()
def report():
    """
    Generate threat intelligence report

    Analyzes threat actors and generates a detailed report.

    Examples:
        itsup monitor report
    """
    logger.info("Generating threat intelligence report...")

    try:
        subprocess.run(["python3", "bin/analyze_threats.py"], check=True)
    except subprocess.CalledProcessError as e:
        logger.error("Failed to generate report")
        sys.exit(e.returncode)
