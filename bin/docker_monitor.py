#!/usr/bin/env python3
"""
Container Security Monitor - Entry Point

Real-time monitoring of container network activity to detect and block malicious connections.

See monitor/ package for implementation details.
"""
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime

# Add parent directory to path for monitor package import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.logging_config import setup_logging
from monitor import (
    BLACKLIST_FILE,
    HONEYPOT_CONTAINER,
    LOG_FILE,
    OPENSNITCH_DB,
    WHITELIST_FILE,
)
from monitor.core import ContainerMonitor
from monitor.iptables import IptablesManager
from monitor.opensnitch import OpenSnitchIntegration


def clear_iptables_rules():
    """
    Clear all iptables rules created by this monitor.

    This removes:
    - The LOG rule for CONTAINER-TCP connections
    - All DROP rules for blacklisted IPs
    """
    print("🧹 Clearing iptables rules...")

    # Use IptablesManager to clear rules
    manager = IptablesManager()
    manager.clear_monitor_rules()

    print("\n✅ iptables cleanup complete")
    print("ℹ️  Note: Blacklist file unchanged, only iptables rules removed")


def cleanup_blacklist():
    """
    Cleanup mode: Identify false positives using OpenSnitch verification.

    Compares blacklist against OpenSnitch's historical block data to identify
    false positives. Uses DNS logs as secondary source.
    """
    print("🧹 Cleanup mode: Analyzing blacklist for false positives...")

    # Create monitor instance to reuse methods
    monitor = ContainerMonitor(skip_sync=True, block=False, use_opensnitch=False)

    # Read blacklist
    blacklisted = monitor.blacklist.get_all()
    print(f"📋 Found {len(blacklisted)} IPs in blacklist")

    # Try PRIMARY source: OpenSnitch DB
    opensnitch_available = False
    opensnitch_blocked_ips = set()

    if os.path.exists(OPENSNITCH_DB):
        print("🔍 PRIMARY: Checking OpenSnitch database...")
        try:
            conn = sqlite3.connect(OPENSNITCH_DB)
            cursor = conn.cursor()

            # Get all ARPA reverse DNS blocks
            cursor.execute(
                """
                SELECT DISTINCT dst_host
                FROM connections
                WHERE rule = 'deny-always-arpa-53'
                AND dst_host LIKE '%.in-addr.arpa'
            """
            )

            rows = cursor.fetchall()
            conn.close()

            # Extract IPs from ARPA queries
            for (dst_host,) in rows:
                ip = OpenSnitchIntegration.extract_ip_from_arpa(dst_host)
                if ip and monitor.is_valid_ip(ip) and not monitor.is_private_ip(ip):
                    opensnitch_blocked_ips.add(ip)

            print(f"✅ Found {len(opensnitch_blocked_ips)} IPs blocked by OpenSnitch (confirmed threats)")
            opensnitch_available = True

        except Exception as e:
            print(f"⚠️  OpenSnitch query failed: {e}")
            print("📋 Falling back to DNS log analysis...")

    # FALLBACK: Parse DNS logs
    print("🔍 SECONDARY: Parsing DNS logs from honeypot...")
    dns_cache = {}

    try:
        result = subprocess.run(["docker", "logs", HONEYPOT_CONTAINER], capture_output=True, text=True, timeout=30)
        dns_logs = result.stdout

        # Build IP → domains mapping
        reply_pattern = re.compile(r"reply ([\w\.\-]+) is ([\d\.]+)")

        for line in dns_logs.split("\n"):
            match = reply_pattern.search(line)
            if match:
                domain, ip = match.groups()
                if monitor.is_valid_ip(ip) and not monitor.is_private_ip(ip):
                    if ip not in dns_cache:
                        dns_cache[ip] = set()
                    dns_cache[ip].add(domain)

        print(f"✅ Found {len(dns_cache)} unique IPs in DNS history")

    except Exception as e:
        print(f"⚠️  Failed to get DNS logs: {e}")
        if not opensnitch_available:
            print("❌ Both OpenSnitch and DNS logs unavailable - cannot proceed")
            sys.exit(1)

    # Analyze blacklist
    to_whitelist = []
    to_keep = []

    for ip in blacklisted:
        # PRIMARY check: Is this IP in OpenSnitch blocks?
        if opensnitch_available:
            if ip in opensnitch_blocked_ips:
                # Confirmed threat - keep in blacklist
                reason = "OpenSnitch blocked reverse DNS"
                print(f"🚨 {ip} → {reason} (CONFIRMED THREAT)")
                to_keep.append(ip)
            else:
                # NOT in OpenSnitch blocks - likely false positive
                domains = dns_cache.get(ip, set())
                if domains:
                    reason = f"DNS: {', '.join(sorted(domains)[:2])}"
                else:
                    reason = "NOT in OpenSnitch blocks"
                print(f"✅ {ip} → {reason} (FALSE POSITIVE)")
                to_whitelist.append((ip, domains if domains else {"unknown"}))
        else:
            # FALLBACK: Use DNS history only
            if ip in dns_cache:
                domains = dns_cache[ip]
                print(f"⚠️  {ip} → {', '.join(sorted(domains)[:3])} (LIKELY FALSE POSITIVE - confirm)")
                to_whitelist.append((ip, domains))
            else:
                print(f"🚨 {ip} → NO DNS history (KEEP IN BLACKLIST)")
                to_keep.append(ip)

    # Summary
    print("\n📊 Summary:")
    if opensnitch_available:
        print("   ✅ Source: OpenSnitch DB (PRIMARY - high confidence)")
    else:
        print("   ⚠️  Source: DNS logs only (FALLBACK - requires confirmation)")
    print(f"   False positives (move to whitelist): {len(to_whitelist)}")
    print(f"   Real threats (keep in blacklist): {len(to_keep)}")

    if to_whitelist:
        if opensnitch_available:
            confirm = input(f"\n❓ Move {len(to_whitelist)} IPs to whitelist? [y/N]: ")
        else:
            print("\n⚠️  WARNING: Using DNS logs only (OpenSnitch unavailable)")
            print("   Some false positives may be missed if DNS logs are incomplete")
            confirm = input(f"\n❓ Move {len(to_whitelist)} IPs to whitelist? [y/N]: ")

        if confirm.lower() == "y":
            # Add to whitelist
            with open(WHITELIST_FILE, "a") as f:
                for ip, domains in to_whitelist:
                    if domains:
                        f.write(f"{ip}  # {', '.join(sorted(domains)[:2])}\n")
                    else:
                        f.write(f"{ip}\n")

            # Remove from blacklist
            with open(BLACKLIST_FILE, "w") as f:
                f.write("# Outbound blacklist - one IP per line\n")
                for ip in sorted(to_keep):
                    f.write(f"{ip}\n")

            print(f"✅ Moved {len(to_whitelist)} IPs to whitelist")
            print(f"✅ Kept {len(to_keep)} IPs in blacklist")
        else:
            print("❌ Cancelled")
    else:
        print("\n✅ No false positives found!")


def main():
    """Main entry point."""
    if os.geteuid() != 0:
        print("Run as root: sudo python3 bin/docker_monitor.py")
        sys.exit(1)

    # Setup logging (with file output)
    setup_logging(log_file=LOG_FILE)

    # Parse command-line flags
    skip_sync = False
    block = False
    use_opensnitch = False

    for arg in sys.argv[1:]:
        if arg == "--cleanup":
            cleanup_blacklist()
            sys.exit(0)
        elif arg == "--clear-iptables":
            clear_iptables_rules()
            sys.exit(0)
        elif arg == "--skip-sync":
            skip_sync = True
        elif arg == "--block":
            block = True
        elif arg == "--use-opensnitch":
            use_opensnitch = True
        else:
            print(f"Unknown flag: {arg}")
            print("\nUsage:")
            print("  sudo python3 bin/docker_monitor.py                       # Detection only (standalone)")
            print("  sudo python3 bin/docker_monitor.py --block               # Detection + iptables blocking")
            print("  sudo python3 bin/docker_monitor.py --use-opensnitch      # Detection + OpenSnitch integration")
            print("  sudo python3 bin/docker_monitor.py --block --use-opensnitch  # Full protection mode")
            print("  sudo python3 bin/docker_monitor.py --skip-sync           # Memory-only mode (no file I/O)")
            print("  sudo python3 bin/docker_monitor.py --cleanup             # Validate blacklist with OpenSnitch")
            print("  sudo python3 bin/docker_monitor.py --clear-iptables      # Remove iptables rules")
            sys.exit(1)

    # Design by contract: If --use-opensnitch is used, DB must exist
    if use_opensnitch and not os.path.exists(OPENSNITCH_DB):
        print(f"❌ OpenSnitch DB not found: {OPENSNITCH_DB}")
        print("   Either install OpenSnitch or run without --use-opensnitch flag")
        sys.exit(1)

    # Initialize log file
    try:
        with open(LOG_FILE, "a") as f:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            f.write(f"[{ts}] Started\n")
        print(f"✓ Log: {LOG_FILE}")
    except Exception as e:
        print(f"Failed to create log: {e}")
        sys.exit(1)

    # Create and run monitor
    monitor = ContainerMonitor(skip_sync=skip_sync, block=block, use_opensnitch=use_opensnitch)
    monitor.run()


if __name__ == "__main__":
    main()
