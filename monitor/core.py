"""
Core monitoring logic for Container Security Monitor.

This module contains the ContainerMonitor class which orchestrates
DNS correlation, threat detection, and container security monitoring.
"""

import json
import logging
import os
import re
import signal
import subprocess
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Optional

from .constants import (
    BLACKLIST_FILE,
    CHECK_CONNECTIONS_INTERVAL,
    CONNECTION_DEDUP_WINDOW,
    CONNECTION_GRACE_PERIOD,
    DNS_CACHE_WINDOW_HOURS,
    DNS_REGISTRY_FILE,
    HONEYPOT_CONTAINER,
    LOG_FILE,
    LOG_LEVEL,
    OPENSNITCH_POLL_INTERVAL,
    PERIODIC_TASK_INTERVAL,
    RECENT_CONNECTIONS_BUFFER_SIZE,
    SERVER_PORTS,
    WHITELIST_FILE,
)
from .iptables import IptablesManager
from .lists import IPList
from .opensnitch import OpenSnitchIntegration

logger = logging.getLogger(__name__)


class ContainerMonitor:
    """
    Orchestrates container security monitoring via DNS correlation.

    Detects hardcoded IP connections (malware indicator) by correlating
    DNS queries with outbound TCP connections.
    """

    def __init__(self, skip_sync: bool = False, report_only: bool = False, use_opensnitch: bool = False):
        """
        Initialize container monitor.

        Args:
            skip_sync: Memory-only mode (no file I/O)
            report_only: Disable iptables blocking (detection only)
            use_opensnitch: Enable OpenSnitch integration
        """
        # Public configuration (set once in __init__)
        self.skip_sync = skip_sync
        self.report_only = report_only
        self.use_opensnitch = use_opensnitch

        # Internal state (all private - use _ prefix)
        self._lock = threading.Lock()
        self._startup_complete = False

        # Container mapping and compromise tracking
        self._container_ips = {}  # IP → container name mapping
        self._reported_compromises = set()  # (container:ip) pairs already alerted on
        self._compromise_count_by_container = defaultdict(int)  # container → alert count
        self._compromised_ips_by_container = defaultdict(list)  # container → [IPs]

        # DNS correlation cache
        self._dns_cache = {}  # {ip: [(domain, timestamp), ...]} - forward DNS lookups

        # Direct connection tracking (journalctl monitoring)
        self._recent_direct_connections = deque(maxlen=RECENT_CONNECTIONS_BUFFER_SIZE)
        self._seen_direct_connections = {}  # (src_ip, dst_ip, dst_port) → timestamp - deduplication

        # Initialize modules
        self.iptables = IptablesManager()

        # Create file locks
        self.blacklist_file_lock = threading.Lock()
        self._dns_registry_file_lock = threading.Lock()

        # Initialize IP lists
        self.blacklist = IPList(
            BLACKLIST_FILE, self.blacklist_file_lock, header_comment="# Outbound blacklist - one IP per line"
        )
        self.whitelist = IPList(
            WHITELIST_FILE,
            threading.Lock(),
            header_comment="# Whitelist - IPs that should not be logged or blocked",
        )

        # Load IP lists
        self.blacklist.load(skip_if_empty=skip_sync)
        self.whitelist.load()

        # Load DNS registry (persistent IP → domains mapping)
        if not skip_sync:
            self._load_dns_registry()

        # Initialize OpenSnitch integration if enabled
        self._opensnitch_blocked_ips = set()  # Read-only validation set
        if use_opensnitch:
            self.opensnitch = OpenSnitchIntegration()
        else:
            self.opensnitch = None

    def is_private_ip(self, ip: str) -> bool:
        """Check if IP is private/internal."""
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        try:
            octets = [int(p) for p in parts]
            if octets[0] == 10 or octets[0] == 127:
                return True
            if octets[0] == 172 and 16 <= octets[1] <= 31:
                return True
            if octets[0] == 192 and octets[1] == 168:
                return True
            if octets[0] == 169 and octets[1] == 254:
                return True
        except ValueError:
            return False
        return False

    def is_valid_ip(self, text: str) -> bool:
        """Check if text is a valid IP address."""
        parts = text.split(".")
        if len(parts) != 4:
            return False
        try:
            return all(0 <= int(p) <= 255 for p in parts)
        except ValueError:
            return False

    def _load_dns_registry(self) -> None:
        """Load DNS registry from JSON file into _dns_cache.

        If registry doesn't exist, populate it from docker logs (initial bootstrap).
        """
        if not os.path.exists(DNS_REGISTRY_FILE):
            logger.info("📋 No existing DNS registry found, bootstrapping from docker logs...")
            self._parse_dns_logs(DNS_CACHE_WINDOW_HOURS)
            self._save_dns_registry()
            return

        try:
            with open(DNS_REGISTRY_FILE, "r") as f:
                registry = json.load(f)

            # Populate _dns_cache with registry data
            # Registry format: {ip: [domains]}
            # Cache format: {ip: [(domain, timestamp), ...]}
            timestamp = datetime.now()
            with self._lock:
                for ip, domains in registry.items():
                    if ip not in self._dns_cache:
                        self._dns_cache[ip] = []
                    for domain in domains:
                        # Only add if not already present
                        existing_domains = [d for d, _ in self._dns_cache[ip]]
                        if domain not in existing_domains:
                            self._dns_cache[ip].append((domain, timestamp))

            unique_ips = len(registry)
            total_domains = sum(len(domains) for domains in registry.values())
            logger.info(f"✅ DNS registry loaded: {unique_ips} IPs, {total_domains} domain mappings")

        except Exception as e:
            logger.error(f"⚠ Error loading DNS registry: {e}")

    def _save_dns_registry(self) -> None:
        """Save DNS registry from _dns_cache to JSON file."""
        try:
            # Extract unique domains per IP from cache
            # Cache format: {ip: [(domain, timestamp), ...]}
            # Registry format: {ip: [domains]}
            registry = {}
            with self._lock:
                for ip, entries in self._dns_cache.items():
                    domains = list(set(domain for domain, _ in entries))
                    if domains:
                        registry[ip] = sorted(domains)

            # Use file lock to prevent concurrent writes
            with self._dns_registry_file_lock:
                with open(DNS_REGISTRY_FILE, "w") as f:
                    json.dump(registry, f, indent=2, sort_keys=True)

            logger.debug(f"💾 DNS registry saved: {len(registry)} IPs")

        except Exception as e:
            logger.error(f"⚠ Error saving DNS registry: {e}")

    def update_container_mapping(self) -> None:
        """Update mapping of container IPs to names."""
        result = subprocess.run(["docker", "ps", "--format", "{{.ID}} {{.Names}}"], capture_output=True, text=True)

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            container_id, container_name = line.split(None, 1)

            inspect = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}",
                    container_id,
                ],
                capture_output=True,
                text=True,
            )
            container_ips = inspect.stdout.strip()
            if container_ips:
                # Map ALL IPs from all networks (we monitor 172.0.0.0/8)
                for ip in container_ips.split():
                    if ip:  # Skip empty strings
                        self._container_ips[ip] = container_name

    def _update_single_container(self, container_id: str) -> None:
        """Update mapping for a single container by ID."""
        # Get container name
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.Name}}", container_id],
            capture_output=True,
            text=True,
        )
        container_name = result.stdout.strip().lstrip("/")  # Docker adds leading slash

        # Get container IPs
        inspect = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}",
                container_id,
            ],
            capture_output=True,
            text=True,
        )
        container_ips = inspect.stdout.strip()

        if container_ips:
            # Container may have multiple IPs (multiple networks) - store each separately
            ips = container_ips.split()
            with self._lock:
                for ip in ips:
                    self._container_ips[ip] = container_name
            logger.debug(f"🔄 Container mapping updated: {', '.join(ips)} → {container_name}")

    def _remove_container_from_mapping(self, container_id: str) -> None:
        """Remove container from mapping when it stops/dies."""
        # Find and remove by container ID
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}",
                container_id,
            ],
            capture_output=True,
            text=True,
        )
        container_ips = result.stdout.strip()

        if container_ips:
            # Container may have multiple IPs - remove all of them
            with self._lock:
                for ip in container_ips.split():
                    removed_name = self._container_ips.pop(ip, None)
                    if removed_name:
                        logger.debug(f"🔄 Container removed from mapping: {ip} ({removed_name})")

    def monitor_docker_events(self) -> None:
        """Monitor Docker events for container start/stop/die to update mappings in real-time."""
        logger.info("🔍 Docker events listener started")

        while True:
            # Start docker events stream (only container events, JSON format)
            proc = subprocess.Popen(
                ["docker", "events", "--filter", "type=container", "--format", "{{json .}}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            try:
                for line in proc.stdout:
                    if not line.strip():
                        continue

                    try:
                        event = json.loads(line)
                        action = event.get("Action", "")
                        container_id = event.get("id", "")
                        container_name = event.get("Actor", {}).get("Attributes", {}).get("name", "unknown")

                        # Handle container start - add to mapping
                        if action == "start":
                            logger.debug(f"🐳 Container started: {container_name}")
                            self._update_single_container(container_id)

                        # Handle container stop/die - remove from mapping
                        elif action in ("stop", "die"):
                            logger.debug(f"🐳 Container stopped: {container_name}")
                            self._remove_container_from_mapping(container_id)

                    except json.JSONDecodeError:
                        logger.error(f"⚠️  Failed to parse Docker event: {line}")
                        continue
                    except Exception as e:
                        logger.error(f"⚠️  Error processing Docker event: {e}")
                        continue

            except Exception as e:
                logger.error(f"❌ Docker events stream disconnected: {e}")
            finally:
                proc.kill()

            # Reconnect after 5 seconds
            logger.info("🔄 Reconnecting to Docker events in 5 seconds...")
            time.sleep(5)

    def get_container_from_ip(self, container_ip: str) -> Optional[str]:
        """Get container name from IP address."""
        return self._container_ips.get(container_ip)

    def _handle_hardcoded_ip_detection(
        self, container_name: str, dst_ip: str, dst_port: str, log_blacklist: bool, is_historical: bool = False
    ) -> bool:
        """Handle detection of hardcoded IP (no DNS history).

        Args:
            container_name: Name of container making the connection
            dst_ip: Destination IP address
            dst_port: Destination port
            log_blacklist: Whether to log when adding to blacklist
            is_historical: Whether this is from historical analysis

        Returns:
            True if detected and handled, False if skipped (e.g., VPN)
        """
        # DIRTY HACK: Skip blacklist and reporting for VPN containers
        if container_name.startswith("vpn-vpn-openvpn-"):
            logger.debug(f"🔓 VPN exclusion: {container_name} → {dst_ip} (skipped)")
            return False

        # Log the detection
        context = "Historical" if is_historical else "Direct"
        logger.warning(
            f"🔍 {context}: {container_name} → {dst_ip}:{dst_port} - NO DNS history (HARDCODED IP - MALWARE?) 🚨"
        )

        self.add_to_blacklist(dst_ip, log_msg=log_blacklist)
        self.report_compromise(container_name, dst_ip, "connection to hardcoded IP (no DNS)")
        return True

    def report_compromise(self, container: str, ip: str, evidence: str) -> None:
        """Report compromised container."""
        key = f"{container}:{ip}"
        if key not in self._reported_compromises:
            self._reported_compromises.add(key)
            with self._lock:
                self._compromise_count_by_container[container] += 1
                if ip not in self._compromised_ips_by_container[container]:
                    self._compromised_ips_by_container[container].append(ip)
            logger.warning(f"🚨 ALERT: {container} connected to blocked IP {ip} ({evidence})")

    def log_suspicious_containers(self) -> None:
        """Log summary of suspicious containers and their target IPs."""
        for container, count in sorted(self._compromise_count_by_container.items(), key=lambda x: x[1], reverse=True):
            ips = self._compromised_ips_by_container.get(container, [])
            logger.info(f"  {container}: {count} alerts")
            for ip in ips:
                logger.info(f"    → {ip}")

    def add_to_blacklist(self, ip: str, log_msg: bool = True) -> None:
        """Add IP to blacklist and optionally block in iptables."""
        # Never blacklist whitelisted IPs
        if self.whitelist.contains(ip):
            return

        # Add to blacklist (handles skip_sync internally)
        persist = not self.skip_sync
        added = self.blacklist.add(ip, persist=persist)

        if not added:
            return  # Already in blacklist

        if log_msg:
            mode_desc = "memory-only" if self.skip_sync else "persistent"
            action = "detected and blocked" if not self.report_only else "detected"

            # Cross-reference with OpenSnitch if enabled
            if self.use_opensnitch and self._opensnitch_blocked_ips:
                if ip in self._opensnitch_blocked_ips:
                    logger.info(f"➕ {action} ({mode_desc}): {ip} ✅ CONFIRMED by OpenSnitch")
                else:
                    logger.warning(f"➕ {action} ({mode_desc}): {ip} ⚠️  NOT in OpenSnitch (needs review)")
            else:
                logger.info(f"➕ {action} ({mode_desc}): {ip}")

        # Block in iptables if enabled
        if not self.report_only:
            self.iptables.add_drop_rule(ip, log=log_msg)

    def check_list_updates(self) -> None:
        """Check if blacklist/whitelist files have been modified."""
        if not self._startup_complete:
            return

        # Check blacklist (skip if --skip-sync)
        if not self.skip_sync and self.blacklist.has_changed():
            logger.info("🔄 Blacklist file changed, reloading...")
            old = self.blacklist.reload()
            added = self.blacklist.get_all() - old
            removed = old - self.blacklist.get_all()

            # Update iptables for changes
            if not self.report_only:
                for ip in removed:
                    self.iptables.remove_drop_rule(ip)
                for ip in added:
                    self.iptables.add_drop_rule(ip, log=True)

        # Check whitelist
        if self.whitelist.has_changed():
            logger.info("🔄 Whitelist file changed, reloading...")
            old = self.whitelist.reload()
            added = self.whitelist.get_all() - old

            if added:
                # Remove newly whitelisted IPs from blacklist
                removed_count = self.blacklist.remove_ips(added)
                if removed_count > 0:
                    logger.info(f"🔄 Removed {removed_count} newly whitelisted IPs from blacklist")

                    # Remove from iptables too
                    if not self.report_only:
                        for ip in added:
                            self.iptables.remove_drop_rule(ip)

    def monitor_honeypot(self) -> None:
        """Monitor DNS honeypot for queries."""
        logger.info(f"🍯 Monitoring DNS honeypot container: {HONEYPOT_CONTAINER}")

        proc = subprocess.Popen(
            ["docker", "logs", "-f", "--tail", "0", HONEYPOT_CONTAINER],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        for line in proc.stdout:
            line = line.strip()

            # Pattern: dnsmasq[N]: reply/cached domain.com is 1.2.3.4
            # Note: reply/cached lines don't include source IP, only query lines do
            # We only care about IPv4 (skip IPv6 with ::)
            reply_match = re.search(r"(?:reply|cached)\s+([^\s]+)\s+is\s+([0-9.]+)(?:\s|$)", line)
            if reply_match:
                domain, ip = reply_match.groups()

                # Skip if IPv6 indicator present (contains ::)
                if "::" in line:
                    continue

                # Validate it's a proper IPv4 address
                if not self.is_valid_ip(ip):
                    continue

                # Add to DNS cache (only if not already present for this IP)
                timestamp = datetime.now()
                is_new = False
                with self._lock:
                    if ip not in self._dns_cache:
                        self._dns_cache[ip] = []
                    # Only add if this domain isn't already cached for this IP
                    existing_domains = [d for d, _ in self._dns_cache[ip]]
                    if domain not in existing_domains:
                        self._dns_cache[ip].append((domain, timestamp))
                        is_new = True

                # Save registry if new entry was added
                if is_new:
                    self._save_dns_registry()

                logger.trace(f"🍯 DNS: {domain} → {ip}")

    def monitor_direct_connections(self) -> None:
        """Monitor journalctl for direct container TCP connections."""
        logger.info("🔍 Monitoring direct container TCP connections via journalctl...")

        proc = subprocess.Popen(
            ["journalctl", "-kf", "-n", "0", "--no-pager", "--output=short-iso-precise"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        pattern = re.compile(r"\[CONTAINER-TCP\].*SRC=([0-9.]+).*DST=([0-9.]+).*SPT=([0-9]+).*DPT=([0-9]+)")

        for line in proc.stdout:
            line = line.strip()
            match = pattern.search(line)
            if not match:
                continue

            src_ip, dst_ip, src_port, dst_port = match.groups()
            src_port = int(src_port)

            # Filter server response traffic (inbound)
            if src_port in SERVER_PORTS:
                continue

            # Skip private IPs
            if self.is_private_ip(dst_ip):
                continue

            # Parse actual event timestamp from journalctl line (microsecond precision)
            # Format: 2025-10-22T23:27:37.817601+0200 hostname kernel: [CONTAINER-TCP] ...
            timestamp_match = re.match(r"^(\S+)", line)
            if timestamp_match:
                try:
                    # Parse ISO timestamp with microseconds (includes timezone)
                    timestamp_str = timestamp_match.group(1)
                    timestamp = datetime.fromisoformat(timestamp_str)
                    # Convert to naive datetime (remove timezone for consistency)
                    timestamp = timestamp.replace(tzinfo=None)
                except ValueError:
                    # Fallback if parsing fails
                    logger.warning(f"⚠️  Could not parse timestamp from: {line[:50]}")
                    timestamp = datetime.now()
            else:
                timestamp = datetime.now()

            # Log stream delay for debugging
            stream_delay = (datetime.now() - timestamp).total_seconds()
            if stream_delay > 2.0:
                logger.debug(f"⚠️  High stream delay: {stream_delay:.1f}s for connection {src_ip} → {dst_ip}")

            connection_tuple = (src_ip, dst_ip, dst_port)

            # Deduplicate
            if connection_tuple in self._seen_direct_connections:
                last_seen = self._seen_direct_connections[connection_tuple]
                if (timestamp - last_seen).total_seconds() < CONNECTION_DEDUP_WINDOW:
                    continue

            self._seen_direct_connections[connection_tuple] = timestamp
            self._recent_direct_connections.append((timestamp, src_ip, dst_ip, dst_port))

    def check_direct_connections(self) -> None:
        """Check recent direct connections against DNS cache and blacklist."""
        while True:
            time.sleep(CHECK_CONNECTIONS_INTERVAL)

            while self._recent_direct_connections:
                timestamp, src_ip, dst_ip, dst_port = self._recent_direct_connections.popleft()

                # Grace period: allow DNS logs time to arrive before checking
                # Use actual event timestamp (from kernel log) to measure real age
                age = (datetime.now() - timestamp).total_seconds()
                if age < CONNECTION_GRACE_PERIOD:
                    # Too young, put it back and skip for now
                    logger.trace(f"⏳ Connection too young ({age:.3f}s < {CONNECTION_GRACE_PERIOD}s), waiting...")
                    self._recent_direct_connections.append((timestamp, src_ip, dst_ip, dst_port))
                    break  # Exit inner loop, wait for next interval

                container_name = self.get_container_from_ip(src_ip) or f"container-{src_ip}"

                # Log actual event age for debugging
                logger.trace(f"🔍 Checking connection (age: {age:.3f}s): {container_name} → {dst_ip}:{dst_port}")

                # Check if already blacklisted
                if self.blacklist.contains(dst_ip):
                    logger.debug(f"🔍 Direct: {container_name} → {dst_ip}:{dst_port} - BLACKLISTED IP 🚨")
                    self.report_compromise(container_name, dst_ip, "direct connection to blacklisted IP")
                    continue

                # Check if in whitelist
                if self.whitelist.contains(dst_ip):
                    logger.info(f"🔍 Direct: {container_name} → {dst_ip}:{dst_port} - whitelisted")
                    continue

                # Check if IP has DNS history
                with self._lock:
                    has_dns = dst_ip in self._dns_cache

                if has_dns:
                    # Get first domain and count total
                    with self._lock:
                        domains = self._dns_cache[dst_ip]
                        domain = domains[0][0]
                        domain_count = len(domains)
                        all_domains = [d for d, _ in domains]

                    # Show "+N more" if multiple domains
                    if domain_count > 1:
                        domain_display = f"{domain} +{domain_count - 1} more"
                    else:
                        domain_display = domain

                    logger.info(f"🔍 Direct: {container_name} → {dst_ip}:{dst_port} - OK (DNS: {domain_display})")

                    # Show all domains in DEBUG log
                    if domain_count > 1:
                        logger.debug(f"  ↳ DNS mappings: {', '.join(all_domains)}")
                else:
                    # NO DNS HISTORY = HARDCODED IP = MALWARE (or VPN)
                    self._handle_hardcoded_ip_detection(container_name, dst_ip, dst_port, log_blacklist=True)

    def _load_opensnitch_blocks(self) -> None:
        """Load OpenSnitch blocked IPs into memory for cross-reference validation."""
        if not self.use_opensnitch:
            return

        try:
            rows = self.opensnitch.get_all_arpa_blocks()

            for dst_host, dst_ip in rows:
                if not dst_host or "in-addr.arpa" not in dst_host:
                    continue

                ip = OpenSnitchIntegration.extract_ip_from_arpa(dst_host)

                if ip and not self.is_private_ip(ip):
                    self._opensnitch_blocked_ips.add(ip)

            logger.info(f"✅ Loaded {len(self._opensnitch_blocked_ips)} OpenSnitch blocked IPs for cross-reference")

        except Exception as e:
            logger.error(f"⚠️  Error loading OpenSnitch blocks: {e}")

    def monitor_opensnitch(self) -> None:
        """Monitor OpenSnitch blocks in real-time and update validation set."""

        def on_block(timestamp: str, dst_host: str, ip: str) -> None:
            """Callback for new OpenSnitch blocks - add to validation set."""
            if self.is_private_ip(ip):
                return

            # Add to validation set
            self._opensnitch_blocked_ips.add(ip)

        self.opensnitch.monitor_blocks(on_block_callback=on_block, poll_interval=OPENSNITCH_POLL_INTERVAL)

    def periodic_tasks(self) -> None:
        """Run periodic maintenance tasks."""
        while True:
            time.sleep(PERIODIC_TASK_INTERVAL)
            self.check_list_updates()
            self.update_container_mapping()

    def _parse_dns_logs(self, hours: int) -> int:
        """Parse DNS honeypot logs and build DNS cache (used for initial bootstrap).

        Returns:
            Number of unique IPs added to cache
        """
        logger.info(f"📋 Parsing DNS honeypot logs (last {hours}h)...")
        try:
            result = subprocess.run(
                ["docker", "logs", "--since", f"{hours}h", HONEYPOT_CONTAINER], capture_output=True, text=True
            )

            dns_count = 0
            for line in result.stdout.split("\n"):
                # Match both "reply" and "cached" responses (IPv4 only)
                reply_match = re.search(r"(?:reply|cached)\s+([^\s]+)\s+is\s+([0-9.]+)(?:\s|$)", line)
                if reply_match:
                    domain, ip = reply_match.groups()

                    # Skip IPv6 addresses
                    if "::" in line:
                        continue

                    # Validate IPv4 address
                    if self.is_valid_ip(ip):
                        timestamp = datetime.now()
                        with self._lock:
                            if ip not in self._dns_cache:
                                self._dns_cache[ip] = []
                            # Only add if this domain isn't already cached for this IP
                            existing_domains = [d for d, _ in self._dns_cache[ip]]
                            if domain not in existing_domains:
                                self._dns_cache[ip].append((domain, timestamp))
                                dns_count += 1

            unique_ips = len(self._dns_cache)
            logger.info(f"✅ DNS cache pre-warmed: {unique_ips} unique IPs, {dns_count} total entries")
            return unique_ips

        except Exception as e:
            logger.error(f"⚠ Error parsing DNS logs: {e}")
            return 0

    def _parse_connection_logs(self, since_arg: str = "") -> set:
        """Parse journalctl logs and extract outbound connections.

        Args:
            since_arg: journalctl --since argument (e.g., "--since '2025-10-22 12:00:00'") or empty for all logs
                      Note: journalctl only supports second precision, microseconds are stripped

        Returns:
            Set of (src_ip, dst_ip, dst_port) tuples
        """
        try:
            cmd = ["journalctl", "-k", "--no-pager"]
            if since_arg:
                cmd.extend(since_arg.split())

            result = subprocess.run(cmd, capture_output=True, text=True)

            pattern = re.compile(r"\[CONTAINER-TCP\].*SRC=([0-9.]+).*DST=([0-9.]+).*SPT=([0-9]+).*DPT=([0-9]+)")
            connections = set()

            for line in result.stdout.split("\n"):
                match = pattern.search(line)
                if not match:
                    continue

                src_ip, dst_ip, src_port, dst_port = match.groups()
                src_port = int(src_port)

                if src_port in SERVER_PORTS:
                    continue

                if self.is_private_ip(dst_ip):
                    continue

                connections.add((src_ip, dst_ip, dst_port))

            return connections

        except Exception as e:
            logger.error(f"⚠ Error parsing connection logs: {e}")
            return set()

    def _get_last_processed_timestamp(self) -> Optional[str]:
        """Get the last processed timestamp from our log file.

        Returns:
            ISO timestamp string or None if no previous run
        """
        try:
            if not os.path.exists(LOG_FILE):
                return None

            # Read last line from log file
            with open(LOG_FILE, "rb") as f:
                f.seek(0, os.SEEK_END)
                file_size = f.tell()
                if file_size == 0:
                    return None

                # Read last 2KB to find last timestamp
                read_size = min(2048, file_size)
                f.seek(-read_size, os.SEEK_END)
                lines = f.read().decode("utf-8", errors="ignore").splitlines()

                # Find last line with timestamp
                for line in reversed(lines):
                    # Format: [2025-10-22 13:32:18.714729] message
                    match = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]", line)
                    if match:
                        return match.group(1)

            return None
        except Exception as e:
            logger.error(f"⚠️  Could not read last timestamp: {e}")
            return None

    def _detect_hardcoded_ips(self, connections: set) -> int:
        """Correlate connections with DNS cache to detect hardcoded IPs.

        Args:
            connections: Set of (src_ip, dst_ip, dst_port) tuples

        Returns:
            Number of hardcoded IPs detected
        """
        hardcoded_count = 0

        for src_ip, dst_ip, dst_port in connections:
            container_name = self.get_container_from_ip(src_ip) or f"container-{src_ip}"

            # Skip if already in blacklist/whitelist
            if self.blacklist.contains(dst_ip) or self.whitelist.contains(dst_ip):
                continue

            # Check DNS cache
            with self._lock:
                has_dns = dst_ip in self._dns_cache

            if not has_dns:
                # NO DNS HISTORY = HARDCODED IP (or VPN)
                if self._handle_hardcoded_ip_detection(container_name, dst_ip, dst_port, log_blacklist=False, is_historical=True):
                    hardcoded_count += 1

        return hardcoded_count

    def collect_historical_data(self) -> None:
        """Collect historical data to detect past threats.

        - DNS cache: already loaded from persistent registry in __init__
        - Connection scan: resume from last processed timestamp (from our log file)
        """
        # Get last processed timestamp
        last_timestamp = self._get_last_processed_timestamp()

        if last_timestamp:
            # Strip microseconds - journalctl only supports second precision
            timestamp_seconds = last_timestamp.split(".")[0]
            logger.info(f"🔍 Resuming from last run: {last_timestamp} (journalctl: {timestamp_seconds})")
            since_arg = f"--since '{timestamp_seconds}'"
        else:
            logger.info("🔍 First run - scanning all available connection logs")
            since_arg = ""

        # Scan past outbound connections (from last timestamp)
        logger.info(f"📋 Scanning outbound connections{' since last run' if last_timestamp else ''}...")
        connections = self._parse_connection_logs(since_arg=since_arg)
        logger.info(f"📋 Found {len(connections)} unique connections to analyze")

        # Detect hardcoded IPs
        hardcoded_count = self._detect_hardcoded_ips(connections)
        mode_desc = "memory-only" if self.skip_sync else "persistent"
        logger.info(f"📊 Detected {hardcoded_count} hardcoded IPs from historical analysis ({mode_desc})")

    def _setup_signal_handlers(self) -> None:
        """Setup SIGINT and SIGTERM handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, lambda s, f: self._cleanup_and_exit())
        signal.signal(signal.SIGTERM, lambda s, f: self._cleanup_and_exit())

    def _setup_iptables(self) -> None:
        """Setup iptables LOG rule for monitoring."""
        self.iptables.ensure_log_rule_exists()

    def _run_historical_analysis(self) -> None:
        """Run historical data collection and analysis."""
        logger.info("🚀 Starting collection phase...")
        self.collect_historical_data()
        logger.info("✅ Collection phase complete")

    def _start_monitoring_threads(self) -> None:
        """Start all monitoring threads."""
        threads = [
            threading.Thread(target=self.monitor_docker_events, daemon=True),
            threading.Thread(target=self.monitor_honeypot, daemon=True),
            threading.Thread(target=self.monitor_direct_connections, daemon=True),
            threading.Thread(target=self.check_direct_connections, daemon=True),
            threading.Thread(target=self.periodic_tasks, daemon=True),
        ]

        # Add OpenSnitch monitoring thread if enabled
        if self.use_opensnitch:
            threads.insert(0, threading.Thread(target=self.monitor_opensnitch, daemon=True))

        for t in threads:
            t.start()

        logger.info("✅ All monitoring threads started")

    def run(self) -> None:
        """Run the container security monitor."""
        logger.info("=== Container Security Monitor with DNS Honeypot Started ===")
        logger.info(f"Log level: {LOG_LEVEL}")

        if self.use_opensnitch:
            logger.info("Monitoring: DNS Honeypot + Direct TCP connections (with OpenSnitch cross-reference)")
        else:
            logger.info("Monitoring: DNS Honeypot + Direct TCP connections (standalone mode)")

        # Setup
        self._setup_signal_handlers()
        self.update_container_mapping()
        self._setup_iptables()

        # Load OpenSnitch blocks for cross-reference if enabled
        if self.use_opensnitch:
            count = self.opensnitch.get_recent_block_count(hours=24)
            logger.info(f"📊 Found {count} blocks in last 24 hours (0-deny-arpa-53)")
            self._load_opensnitch_blocks()

        # Historical analysis
        self._run_historical_analysis()

        # Start real-time monitoring
        logger.info("✅ Entering real-time monitoring...")
        self._startup_complete = True
        self._start_monitoring_threads()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\n=== Monitor stopped ===")
            if self._compromise_count_by_container:
                logger.info("Suspicious containers detected:")
                self.log_suspicious_containers()

    def _cleanup_and_exit(self) -> None:
        """Cleanup handler for signals."""
        logger.info("\n=== Shutting down ===")
        logger.info("ℹ️  iptables rules remain active (use --clear-iptables to remove)")
        if self._compromise_count_by_container:
            logger.info("Suspicious containers detected:")
            self.log_suspicious_containers()
        exit(0)
