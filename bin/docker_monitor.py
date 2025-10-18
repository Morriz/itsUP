#!/usr/bin/env python3
"""
Container Security Monitor with DNS Honeypot Integration

Real-time monitoring of container network activity to detect and block malicious connections.

Modes:
    Normal (real-time):     sudo python3 bin/docker_monitor.py
    Cleanup (sweeping):     sudo python3 bin/docker_monitor.py --cleanup
    Clear iptables rules:   sudo python3 bin/docker_monitor.py --clear-iptables

Normal mode startup sequence:
1. Collects DNS history (last 24h) to pre-warm DNS cache
2. Scans journalctl connections (last 24h) for hardcoded IPs
3. Auto-blacklists any true positives found
4. Enters real-time monitoring with warm cache (no false positives)

Real-time monitoring tracks:
- OpenSnitch reverse DNS blocks (ARPA queries)
- DNS honeypot queries and replies
- Direct TCP connections via iptables/journalctl
- Correlates all sources to detect hardcoded IPs (malware)

Cleanup mode:
- Analyzes complete DNS history (all logs)
- Identifies false positives in blacklist
- Interactively moves legitimate IPs to whitelist

Clear iptables mode:
- Removes LOG rule (stops journalctl monitoring)
- Removes all DROP rules for blacklisted IPs
- Use when you want to stop monitoring or clean logs

Files:
- data/blacklist-outbound-ips.txt (real threats)
- data/whitelist-outbound-ips.txt (false positives)
- /var/log/compromised_container.log (monitor logs)
"""
import os
import re
import signal
import sqlite3
import subprocess
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta

from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

LOG_FILE = "/var/log/compromised_container.log"
OPENSNITCH_DB = os.getenv("OPENSNITCH_DB", "/var/lib/opensnitch/opensnitch.sqlite3")
HONEYPOT_CONTAINER = "dns-honeypot"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLACKLIST_FILE = os.path.join(PROJECT_ROOT, "data", "blacklist-outbound-ips.txt")
WHITELIST_FILE = os.path.join(PROJECT_ROOT, "data", "whitelist-outbound-ips.txt")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")  # DEBUG or INFO


class ContainerMonitor:
    # Traefik's listening port (when SPT=8443, it's responding to inbound traffic)
    SERVER_PORTS = {8443}

    def __init__(self):
        self.blocked_ips = set()
        self.blacklisted_ips = set()  # IPs in blacklist file
        self.whitelisted_ips = set()  # IPs in whitelist file
        self.blacklist_mtime = 0
        self.whitelist_mtime = 0
        self.lock = threading.Lock()
        self.blacklist_file_lock = threading.Lock()  # File write lock
        self.startup_complete = False  # Prevent check_list_updates during startup
        self.reported = set()
        self.connections = defaultdict(list)
        self.container_ips = {}
        self.suspect_containers = defaultdict(int)
        self.honeypot_queries = []  # Store recent honeypot queries for correlation
        self.dns_cache = {}  # {ip: [(domain, timestamp), ...]} - forward DNS cache
        self.recent_direct_connections = deque(maxlen=100)  # (timestamp, src_ip, dst_ip, dst_port)
        self.seen_direct_connections = {}  # (src_ip, dst_ip, dst_port) -> timestamp
        self.iptables_rule_added = False
        self.load_blacklist()
        self.load_whitelist()

    def log(self, message: str, level: str = "INFO") -> None:
        """Log message with level filtering. Levels: DEBUG, INFO"""
        if level == "DEBUG" and LOG_LEVEL != "DEBUG":
            return
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        with open(LOG_FILE, "a") as f:
            f.write(f"[{ts}] {message}\n")
        print(f"[{ts}] {message}")

    def load_blacklist(self) -> None:
        """Load existing blacklisted IPs from file"""
        try:
            import os

            stat = os.stat(BLACKLIST_FILE)
            self.blacklist_mtime = stat.st_mtime

            new_blacklist = set()
            with open(BLACKLIST_FILE, "r") as f:
                for line in f:
                    ip = line.strip()
                    if ip and not ip.startswith("#"):
                        new_blacklist.add(ip)

            with self.lock:
                old_blacklist = self.blacklisted_ips
                self.blacklisted_ips = new_blacklist

            # Check for removals
            removed = old_blacklist - new_blacklist
            for ip in removed:
                self.remove_ip_from_iptables(ip)

            # Check for additions
            added = new_blacklist - old_blacklist
            for ip in added:
                self.block_ip_in_iptables(ip, log=True)

            if new_blacklist and not old_blacklist:
                self.log(f"📋 Loaded {len(new_blacklist)} IPs from blacklist")
            elif added or removed:
                self.log(f"📋 Blacklist updated: +{len(added)} -{len(removed)} (total: {len(new_blacklist)})")

        except FileNotFoundError:
            # Create empty file
            try:
                with open(BLACKLIST_FILE, "w") as f:
                    f.write("# OpenSnitch blacklist - one IP per line\n")
                self.log(f"✅ Created blacklist file: {BLACKLIST_FILE}")
            except Exception as e:
                self.log(f"❌ Could not create blacklist: {e}")
        except Exception as e:
            self.log(f"⚠️ Error loading blacklist: {e}")

    def load_whitelist(self) -> None:
        """Load whitelisted IPs from file and remove from blacklist"""
        try:
            import os

            stat = os.stat(WHITELIST_FILE)
            self.whitelist_mtime = stat.st_mtime

            new_whitelist = set()
            with open(WHITELIST_FILE, "r") as f:
                for line in f:
                    ip = line.strip()
                    # Extract IP from line (ignore comments after IP)
                    if ip and not ip.startswith("#"):
                        ip_part = ip.split("#")[0].strip()
                        if ip_part:
                            new_whitelist.add(ip_part)

            with self.lock:
                old_whitelist = self.whitelisted_ips
                self.whitelisted_ips = new_whitelist

            # Check for newly whitelisted IPs
            added = new_whitelist - old_whitelist
            if added:
                # Remove from blacklist file (which will trigger load_blacklist via check_list_updates)
                with self.blacklist_file_lock:
                    current_blacklist = self._read_blacklist_file()
                    updated_blacklist = current_blacklist - added

                    if len(updated_blacklist) < len(current_blacklist):
                        # Rewrite blacklist file without whitelisted IPs
                        # This file change will trigger load_blacklist() which handles:
                        # - Updating self.blacklisted_ips in memory
                        # - Removing iptables DROP rules
                        with open(BLACKLIST_FILE, "w") as f:
                            f.write("# OpenSnitch blacklist - one IP per line\n")
                            for ip in sorted(updated_blacklist):
                                f.write(f"{ip}\n")

                        self.log(f"🔄 Removed {len(added)} newly whitelisted IPs from blacklist")

            if new_whitelist and not old_whitelist:
                self.log(f"📋 Loaded {len(new_whitelist)} IPs from whitelist")
            elif added:
                self.log(f"📋 Whitelist updated: +{len(added)} (total: {len(new_whitelist)})")

        except FileNotFoundError:
            # Create empty file
            try:
                with open(WHITELIST_FILE, "w") as f:
                    f.write("# Whitelist - IPs that should not be logged or blocked\n")
                self.log(f"✅ Created whitelist file: {WHITELIST_FILE}")
            except Exception as e:
                self.log(f"❌ Could not create whitelist: {e}")
        except Exception as e:
            self.log(f"⚠️ Error loading whitelist: {e}")

    def check_list_updates(self) -> None:
        """Check if blacklist/whitelist files have been modified"""
        if not self.startup_complete:
            return  # Skip during startup sync

        try:
            import os

            # Check blacklist
            if os.path.exists(BLACKLIST_FILE):
                stat = os.stat(BLACKLIST_FILE)
                if stat.st_mtime > self.blacklist_mtime:
                    self.log("🔄 Blacklist file changed, reloading...")
                    self.load_blacklist()

            # Check whitelist
            if os.path.exists(WHITELIST_FILE):
                stat = os.stat(WHITELIST_FILE)
                if stat.st_mtime > self.whitelist_mtime:
                    self.log("🔄 Whitelist file changed, reloading...")
                    self.load_whitelist()

        except Exception as e:
            self.log(f"⚠️ Error checking list updates: {e}")

    def _read_blacklist_file(self) -> set:
        """Read blacklist file and return set of IPs (DRY helper)"""
        try:
            with open(BLACKLIST_FILE, "r") as f:
                return {line.strip() for line in f if line.strip() and not line.startswith("#")}
        except FileNotFoundError:
            return set()

    def add_to_blacklist(self, ip: str, log_msg: bool = True) -> None:
        """Add IP to OpenSnitch blacklist file and block in iptables (atomic)"""
        # Never blacklist whitelisted IPs
        with self.lock:
            if ip in self.whitelisted_ips:
                return

        try:
            # Atomic file operation with lock
            with self.blacklist_file_lock:
                # Read current file contents
                existing_ips = self._read_blacklist_file()

                if ip in existing_ips:
                    return  # Already in file

                # Append to file atomically
                with open(BLACKLIST_FILE, "a") as f:
                    f.write(f"{ip}\n")

                # Update in-memory set
                with self.lock:
                    self.blacklisted_ips.add(ip)

            if log_msg:
                self.log(f"➕ Added {ip} to blacklist")

            # Block in iptables for containers
            self.block_ip_in_iptables(ip, log=log_msg)
        except Exception as e:
            self.log(f"❌ Failed to add {ip} to blacklist: {e}")

    def extract_ip_from_arpa(self, query: str) -> str | None:
        pattern = r"(\d+)\.(\d+)\.(\d+)\.(\d+)\.in-addr\.arpa"
        match = re.match(pattern, query)
        if match:
            return f"{match.group(4)}.{match.group(3)}.{match.group(2)}.{match.group(1)}"
        return None

    def is_private_ip(self, ip: str) -> bool:
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
        parts = text.split(".")
        if len(parts) != 4:
            return False
        try:
            return all(0 <= int(p) <= 255 for p in parts)
        except ValueError:
            return False

    def update_container_mapping(self) -> None:
        result = subprocess.run(["docker", "ps", "--format", "{{.ID}} {{.Names}}"], capture_output=True, text=True)

        new_mapping = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                cid, cname = parts

                inspect = subprocess.run(
                    ["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}", cid],
                    capture_output=True,
                    text=True,
                )
                ips = inspect.stdout.strip().split()

                for c_ip in ips:
                    if c_ip and c_ip.strip():
                        new_mapping[c_ip.strip()] = cname

        with self.lock:
            self.container_ips = new_mapping

    def get_container_from_ip(self, container_ip: str) -> str | None:
        with self.lock:
            return self.container_ips.get(container_ip)

    def report_compromise(self, container: str, ip: str, evidence: str) -> None:
        key = f"{container}:{ip}"
        if key not in self.reported:
            self.reported.add(key)
            with self.lock:
                self.suspect_containers[container] += 1
            self.log(f"🚨 ALERT: {container} connected to blocked IP {ip} ({evidence})")

    def monitor_honeypot(self) -> None:
        self.log(f"🍯 Monitoring DNS honeypot container: {HONEYPOT_CONTAINER}", "INFO")

        proc = subprocess.Popen(
            ["docker", "logs", "-f", "--tail", "0", HONEYPOT_CONTAINER],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # Pattern: 2025-10-17 12:44:05. dnsmasq[17]: query[PTR] 89.10.148.45.in-addr.arpa from 172.30.0.28
        query_pattern = re.compile(
            r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+ dnsmasq\[\d+\]: query\[(\w+)\] ([\w\.\-]+) from ([\d\.]+)"
        )
        # Pattern: 2025-10-17 12:44:05 dnsmasq[11]: reply registry.npmjs.org is 104.16.3.35
        reply_pattern = re.compile(
            r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+dnsmasq\[\d+\]: reply ([\w\.\-]+) is ([\d\.]+)"
        )

        try:
            for line in proc.stdout:
                # Check for reply lines first (to populate cache)
                reply_match = reply_pattern.search(line)
                if reply_match:
                    timestamp_str, domain, ip = reply_match.groups()
                    if self.is_valid_ip(ip) and not self.is_private_ip(ip):
                        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                        with self.lock:
                            if ip not in self.dns_cache:
                                self.dns_cache[ip] = []
                            self.dns_cache[ip].append((domain, timestamp))
                        self.log(f"🔍 DNS reply: {domain} → {ip}", "DEBUG")
                    continue

                # Check for query lines
                match = query_pattern.search(line)
                if match:
                    timestamp_str, query_type, query_domain, source_ip = match.groups()

                    # Check if this is a reverse DNS query
                    if "in-addr.arpa" in query_domain:
                        queried_ip = self.extract_ip_from_arpa(query_domain)

                        # Only process non-private IPs
                        if queried_ip and not self.is_private_ip(queried_ip):
                            # Skip whitelisted IPs
                            with self.lock:
                                if queried_ip in self.whitelisted_ips:
                                    continue

                            container_name = self.get_container_from_ip(source_ip)

                            if container_name:
                                # Store for correlation
                                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                                with self.lock:
                                    self.honeypot_queries.append(
                                        (timestamp, query_domain, source_ip, container_name, queried_ip)
                                    )

                                # Check if OpenSnitch blocked it
                                self.correlate_honeypot_with_opensnitch(
                                    timestamp, query_domain, container_name, queried_ip
                                )

        except KeyboardInterrupt:
            proc.terminate()
        except Exception as e:
            self.log(f"❌ Honeypot monitor error: {e}")

    def correlate_honeypot_with_opensnitch(self, query_time, query_domain, container_name, malware_ip):
        """Check if OpenSnitch blocked this query within a few seconds"""
        try:
            conn = sqlite3.connect(OPENSNITCH_DB)
            cursor = conn.cursor()

            # Look for blocks within 5 seconds of the query
            time_min = (query_time - timedelta(seconds=2)).isoformat()
            time_max = (query_time + timedelta(seconds=5)).isoformat()

            cursor.execute(
                """
                SELECT time, action, dst_host, process
                FROM connections
                WHERE dst_host = ?
                AND time BETWEEN ? AND ?
                ORDER BY time ASC
                LIMIT 1
            """,
                (query_domain, time_min, time_max),
            )

            row = cursor.fetchone()
            conn.close()

            if row:
                block_time, action, dst_host, process = row
                if action == "deny":
                    self.log(
                        f"🍯 Reverse DNS: {container_name} queried {query_domain} → {malware_ip} ⚠️ BLOCKED! 🚨", "INFO"
                    )
                    self.add_to_blacklist(malware_ip)
                    self.report_compromise(
                        container_name, malware_ip, f"honeypot logged query, OpenSnitch blocked via {process}"
                    )
            else:
                self.log(f"🍯 Reverse DNS: {container_name} queried {query_domain} → {malware_ip}", "DEBUG")
        except Exception as e:
            self.log(f"Correlation error: {e}")

    def check_iptables_log_rule_exists(self) -> bool:
        """Check if the LOG rule already exists in iptables"""
        try:
            result = subprocess.run(
                [
                    "iptables",
                    "-C",
                    "DOCKER-USER",
                    "-s",
                    "172.0.0.0/8",
                    "-p",
                    "tcp",
                    "-m",
                    "conntrack",
                    "--ctstate",
                    "NEW",
                    "-j",
                    "LOG",
                    "--log-prefix",
                    "[CONTAINER-TCP] ",
                    "--log-level",
                    "4",
                ],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception:
            return False

    def add_iptables_rule(self) -> None:
        """Add iptables rule to log NEW outbound container TCP connections (idempotent)"""
        # Check if rule already exists
        if self.check_iptables_log_rule_exists():
            self.log("✅ iptables LOG rule already exists (persistent across restarts)")
            self.iptables_rule_added = True
            return

        try:
            cmd = [
                "iptables",
                "-I",
                "DOCKER-USER",
                "1",
                "-s",
                "172.0.0.0/8",
                "-p",
                "tcp",
                "-m",
                "conntrack",
                "--ctstate",
                "NEW",
                "-j",
                "LOG",
                "--log-prefix",
                "[CONTAINER-TCP] ",
                "--log-level",
                "4",
            ]
            subprocess.run(cmd, check=True)
            self.iptables_rule_added = True
            self.log("✅ Added iptables LOG rule for NEW outbound container TCP connections")
        except Exception as e:
            self.log(f"❌ Failed to add iptables LOG rule: {e}")

    def check_ip_blocked_in_iptables(self, ip: str) -> bool:
        """Check if IP already has a DROP rule in iptables"""
        try:
            result = subprocess.run(
                ["iptables", "-C", "DOCKER-USER", "-s", "172.0.0.0/8", "-d", ip, "-j", "DROP"],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception:
            return False

    def block_ip_in_iptables(self, ip: str, log: bool = True) -> None:
        """Add iptables DROP rule for blacklisted IP (idempotent)"""
        # Check if rule already exists
        if self.check_ip_blocked_in_iptables(ip):
            if log:
                self.log(f"✅ {ip} already blocked in iptables", "DEBUG")
            return

        try:
            # Add rule to DROP traffic to this IP (before the LOG rule)
            cmd = ["iptables", "-I", "DOCKER-USER", "1", "-s", "172.0.0.0/8", "-d", ip, "-j", "DROP"]
            subprocess.run(cmd, check=True)
            if log:
                self.log(f"🚫 Blocked {ip} in iptables")
        except Exception as e:
            self.log(f"❌ Failed to block {ip} in iptables: {e}")

    def remove_ip_from_iptables(self, ip: str) -> None:
        """Remove iptables DROP rule for IP"""
        try:
            cmd = ["iptables", "-D", "DOCKER-USER", "-s", "172.0.0.0/8", "-d", ip, "-j", "DROP"]
            subprocess.run(cmd, check=False)  # Don't fail if rule doesn't exist
            self.log(f"✅ Unblocked {ip} in iptables")
        except Exception as e:
            self.log(f"⚠️ Failed to unblock {ip} in iptables: {e}")

    def remove_iptables_rule(self) -> None:
        """Remove the iptables rule"""
        if not self.iptables_rule_added:
            return
        try:
            cmd = [
                "iptables",
                "-D",
                "DOCKER-USER",
                "-s",
                "172.0.0.0/8",
                "-p",
                "tcp",
                "-m",
                "conntrack",
                "--ctstate",
                "NEW",
                "-j",
                "LOG",
                "--log-prefix",
                "[CONTAINER-TCP] ",
                "--log-level",
                "4",
            ]
            subprocess.run(cmd, check=False)
            self.log("✅ Removed iptables rule")
        except Exception as e:
            self.log(f"⚠ Failed to remove iptables rule: {e}")

    def monitor_direct_connections(self) -> None:
        """Monitor journalctl for direct container TCP connections"""
        self.log("🔍 Monitoring direct container TCP connections via journalctl...", "INFO")

        proc = subprocess.Popen(
            ["journalctl", "-kf", "-n", "0", "--no-pager"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # Match both SPT and DPT to detect response traffic
        pattern = re.compile(r"\[CONTAINER-TCP\].*SRC=([0-9.]+).*DST=([0-9.]+).*SPT=([0-9]+).*DPT=([0-9]+)")

        try:
            for line in iter(proc.stdout.readline, ""):
                if not line:
                    break
                match = pattern.search(line)
                if match:
                    src_ip, dst_ip, src_port, dst_port = match.groups()
                    src_port = int(src_port)
                    dst_port = int(dst_port)

                    # Skip response traffic (SPT is a server port = container is responding, not initiating)
                    if src_port in self.SERVER_PORTS:
                        self.log(f"⬅️  Response traffic: {src_ip}:{src_port} → {dst_ip}:{dst_port} (INBOUND connection response)", "DEBUG")
                        continue

                    # Filter out private IPs (only track external connections)
                    if self.is_private_ip(dst_ip):
                        continue

                    # Skip whitelisted IPs
                    with self.lock:
                        if dst_ip in self.whitelisted_ips:
                            continue

                    timestamp = datetime.now()
                    conn_key = (src_ip, dst_ip, dst_port)

                    # Deduplicate - only store unique connections (not every packet)
                    with self.lock:
                        last_seen = self.seen_direct_connections.get(conn_key)

                        # Only store if new or not seen in last 30 seconds
                        if not last_seen or (timestamp - last_seen).total_seconds() > 30:
                            self.seen_direct_connections[conn_key] = timestamp
                            self.recent_direct_connections.append((timestamp, src_ip, dst_ip, dst_port))

                            # Don't log here - will log only when checking correlation

        except KeyboardInterrupt:
            proc.terminate()
        except Exception as e:
            self.log(f"❌ Direct connection monitor error: {e}")
        finally:
            proc.terminate()

    def check_direct_connections(self) -> None:
        """Periodically check direct connections for hardcoded IPs and blacklisted targets"""
        while True:
            time.sleep(2)

            with self.lock:
                if not self.recent_direct_connections:
                    continue

                # Copy to avoid holding lock, then clear the deque
                connections = list(self.recent_direct_connections)
                self.recent_direct_connections.clear()
                dns_cache_copy = dict(self.dns_cache)

            try:
                for timestamp, src_ip, dst_ip, dst_port in connections:
                    container_name = self.get_container_from_ip(src_ip)
                    if not container_name:
                        continue

                    # Check if this IP has ANY DNS history (cache is kept indefinitely)
                    if dst_ip in dns_cache_copy:
                        domains = [d for d, _ in dns_cache_copy[dst_ip]]
                        self.log(f"🌐 Direct IP: {container_name} → {dst_ip}:{dst_port} (via {domains[0]})", "DEBUG")
                    else:
                        # HARDCODED IP - no DNS lookup ever seen!
                        self.add_to_blacklist(dst_ip, log_msg=True)
                        self.report_compromise(container_name, dst_ip, "direct connection to hardcoded IP")

            except Exception as e:
                self.log(f"Direct connection check error: {e}")

    def monitor_opensnitch(self) -> None:
        self.log("📋 Monitoring OpenSnitch blocks...")

        try:
            conn = sqlite3.connect(OPENSNITCH_DB)
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(time) FROM connections WHERE rule = 'deny-always-arpa-53'")
            last_time = cursor.fetchone()[0] or ""
            conn.close()
            self.log(f"📋 Starting from timestamp: {last_time}")
        except Exception as e:
            self.log(f"⚠ Could not get initial timestamp: {e}")
            last_time = ""

        poll_count = 0

        while True:
            try:
                conn = sqlite3.connect(OPENSNITCH_DB)
                cursor = conn.cursor()

                cursor.execute("SELECT MAX(time) FROM connections WHERE rule = 'deny-always-arpa-53'")

                cursor.execute(
                    """
                    SELECT time, dst_host, dst_ip, dst_port, protocol, process
                    FROM connections
                    WHERE time > ?
                    AND rule = 'deny-always-arpa-53'
                    ORDER BY time ASC
                """,
                    (last_time,),
                )

                rows = cursor.fetchall()
                conn.close()

                for row in rows:
                    timestamp, dst_host = row
                    last_time = timestamp

                    # ONLY process ARPA reverse DNS blocks
                    if dst_host and "in-addr.arpa" in dst_host:
                        ip = self.extract_ip_from_arpa(dst_host)

                        if not ip or self.is_private_ip(ip):
                            continue

                        with self.lock:
                            is_new = ip not in self.blocked_ips
                            if is_new:
                                self.blocked_ips.add(ip)

                        if is_new:
                            # Check if this IP was seen in container forward DNS (last 5 seconds)
                            found_in_cache = False
                            with self.lock:
                                if ip in self.dns_cache:
                                    now = datetime.strptime(timestamp[:19], "%Y-%m-%d %H:%M:%S")
                                    # Check if any domain resolved to this IP in last 5 seconds
                                    for domain, dns_time in self.dns_cache[ip]:
                                        if (now - dns_time).total_seconds() <= 5:
                                            found_in_cache = True
                                            self.log(
                                                f"📋 Host reverse DNS for {ip} (container queried: {domain}) - FALSE POSITIVE",
                                                "INFO",
                                            )
                                            # Add to whitelist instead of blacklist
                                            with open(WHITELIST_FILE, "a") as f:
                                                f.write(f"{ip}\n")
                                            self.whitelisted_ips.add(ip)
                                            break

                            if not found_in_cache:
                                # NO forward DNS seen - hardcoded IP - real threat!
                                self.log(
                                    f"📋 Host reverse DNS for {ip} - NO container forward query (HARDCODED IP - MALWARE!) 🚨",
                                    "INFO",
                                )
                                self.add_to_blacklist(ip, log_msg=False)

                poll_count += 1
                if poll_count % 100 == 0:
                    self.log(f"📋 Heartbeat: Polled {poll_count} times, last={last_time[:19]}", "INFO")

            except Exception as e:
                self.log(f"❌ OpenSnitch error: {e}")

            time.sleep(0.5)

    def periodic_tasks(self) -> None:
        while True:
            self.update_container_mapping()
            self.check_list_updates()

            # Clean old data (keep last 5 minutes)
            cutoff = datetime.now() - timedelta(minutes=5)
            with self.lock:
                self.honeypot_queries = [q for q in self.honeypot_queries if q[0] > cutoff]

                # DNS cache is kept indefinitely - once we see a DNS lookup for an IP,
                # that IP is considered legitimate forever (within this session).
                # This prevents false positives on services with infrequent DNS queries.

                # Clean old direct connection tracking
                self.seen_direct_connections = {
                    k: v for k, v in self.seen_direct_connections.items() if (datetime.now() - v).total_seconds() < 300
                }

            if int(time.time()) % 300 == 0:
                with self.lock:
                    if self.suspect_containers:
                        self.log("📊 Suspicious Activity Summary:")
                        for container, count in sorted(
                            self.suspect_containers.items(), key=lambda x: x[1], reverse=True
                        ):
                            self.log(f"   {container}: {count} suspicious connections")

            time.sleep(10)

    def collect_historical_data(self, hours: int = 24) -> None:
        """
        Pre-warm DNS cache and detect past threats from historical data.

        This runs on every startup to:
        1. Populate DNS cache with recent forward lookups (prevent false positives)
        2. Detect hardcoded IPs from past connections (catch missed threats)

        Args:
            hours: How many hours back to analyze (default: 24)
        """
        self.log(f"🔍 Collecting historical data (last {hours}h)...")

        # 1. Parse DNS honeypot logs to build DNS cache
        self.log("📋 Parsing DNS honeypot logs...")
        try:
            result = subprocess.run(
                ["docker", "logs", "--since", f"{hours}h", HONEYPOT_CONTAINER],
                capture_output=True,
                text=True,
                timeout=30,
            )
            dns_logs = result.stdout
        except Exception as e:
            self.log(f"⚠️ Failed to get DNS logs: {e}")
            return

        # Build DNS cache from reply lines
        reply_pattern = re.compile(
            r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+dnsmasq\[\d+\]: reply ([\w\.\-]+) is ([\d\.]+)"
        )

        dns_entries = 0
        for line in dns_logs.split("\n"):
            match = reply_pattern.search(line)
            if match:
                timestamp_str, domain, ip = match.groups()
                if self.is_valid_ip(ip) and not self.is_private_ip(ip):
                    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    with self.lock:
                        if ip not in self.dns_cache:
                            self.dns_cache[ip] = []
                        self.dns_cache[ip].append((domain, timestamp))
                    dns_entries += 1

        self.log(f"✅ DNS cache pre-warmed: {len(self.dns_cache)} unique IPs, {dns_entries} total entries")

        # 2. Parse journalctl for past NEW TCP connections
        self.log("📋 Scanning past outbound connections...")
        try:
            # Get journalctl logs from last N hours
            since_time = datetime.now() - timedelta(hours=hours)
            since_str = since_time.strftime("%Y-%m-%d %H:%M:%S")

            result = subprocess.run(
                ["journalctl", "-k", "--since", since_str, "--no-pager"], capture_output=True, text=True, timeout=30
            )
            journalctl_logs = result.stdout
        except Exception as e:
            self.log(f"⚠️ Failed to get journalctl logs: {e}")
            return

        # Parse for CONTAINER-TCP connections (match SPT to filter response traffic)
        pattern = re.compile(r"\[CONTAINER-TCP\].*SRC=([0-9.]+).*DST=([0-9.]+).*SPT=([0-9]+).*DPT=([0-9]+)")

        # Track unique connections: (src_ip, dst_ip, dst_port) -> timestamp
        past_connections = {}

        # Extract timestamps from journalctl lines
        timestamp_pattern = re.compile(r"^(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})")

        for line in journalctl_logs.split("\n"):
            match = pattern.search(line)
            if not match:
                continue

            src_ip, dst_ip, src_port, dst_port = match.groups()
            src_port = int(src_port)
            dst_port = int(dst_port)

            # Skip response traffic (SPT is a server port = inbound connection response)
            if src_port in self.SERVER_PORTS:
                continue

            # Skip private IPs and whitelisted
            if self.is_private_ip(dst_ip):
                continue

            with self.lock:
                if dst_ip in self.whitelisted_ips:
                    continue

            # Extract timestamp from journalctl line
            ts_match = timestamp_pattern.match(line)
            if ts_match:
                # Parse syslog timestamp (e.g., "Oct 18 12:34:56")
                ts_str = ts_match.group(1)
                try:
                    # Add current year
                    current_year = datetime.now().year
                    timestamp = datetime.strptime(f"{current_year} {ts_str}", "%Y %b %d %H:%M:%S")
                except ValueError:
                    timestamp = datetime.now()
            else:
                timestamp = datetime.now()

            conn_key = (src_ip, dst_ip, dst_port)
            if conn_key not in past_connections:
                past_connections[conn_key] = timestamp

        self.log(f"📋 Found {len(past_connections)} unique past connections")

        # 3. Cross-reference connections with DNS cache and blacklist hardcoded IPs
        ips_without_dns = []
        for (src_ip, dst_ip, dst_port), conn_time in past_connections.items():
            # Skip if already blacklisted
            with self.lock:
                if dst_ip in self.blacklisted_ips:
                    continue

            # Check if this IP has DNS history
            found_in_dns = False
            with self.lock:
                if dst_ip in self.dns_cache:
                    found_in_dns = True

            if not found_in_dns:
                container_name = self.get_container_from_ip(src_ip)
                if container_name:
                    ips_without_dns.append((container_name, dst_ip, dst_port))
                    # Log and blacklist hardcoded IP
                    self.log(
                        f"🔍 Historical: {container_name} → {dst_ip}:{dst_port} - NO DNS history (HARDCODED IP - MALWARE!) 🚨",
                        "INFO",
                    )
                    self.add_to_blacklist(dst_ip, log_msg=False)
                    self.report_compromise(container_name, dst_ip, "historical connection to hardcoded IP")

        if ips_without_dns:
            self.log(f"📊 Blacklisted {len(ips_without_dns)} hardcoded IPs from historical analysis")
        else:
            self.log("✅ All past connections have DNS history")

    def sync_opensnitch_blocks_to_blacklist(self) -> None:
        """Sync ONLY ARPA reverse DNS blocked IPs to blacklist - ATOMIC"""
        try:
            conn = sqlite3.connect(OPENSNITCH_DB)
            cursor = conn.cursor()

            # Get ONLY reverse DNS (ARPA) blocks from deny-always-arpa-53 rule
            cursor.execute(
                """
                SELECT DISTINCT dst_host, dst_ip
                FROM connections
                WHERE rule = 'deny-always-arpa-53'
                AND dst_host LIKE '%.in-addr.arpa'
            """
            )

            rows = cursor.fetchall()
            conn.close()

            # Atomic operation - read file once, write once
            with self.blacklist_file_lock:
                existing_ips = self._read_blacklist_file()

                new_ips = []
                for dst_host, dst_ip in rows:
                    ip = None

                    # Extract IP from ARPA reverse DNS ONLY
                    if dst_host and "in-addr.arpa" in dst_host:
                        ip = self.extract_ip_from_arpa(dst_host)

                    # Skip if no valid IP, private IP, whitelisted, or already in file
                    if not ip or self.is_private_ip(ip) or ip in existing_ips:
                        continue

                    with self.lock:
                        if ip in self.whitelisted_ips:
                            continue

                    new_ips.append(ip)

                # Write all new IPs at once (single atomic operation)
                if new_ips:
                    self.log(f"🔄 Syncing {len(new_ips)} IPs from OpenSnitch to blacklist...")
                    with open(BLACKLIST_FILE, "a") as f:
                        for ip in new_ips:
                            f.write(f"{ip}\n")

                    # Update in-memory set and iptables
                    with self.lock:
                        self.blacklisted_ips.update(new_ips)

                    for ip in new_ips:
                        self.block_ip_in_iptables(ip, log=False)

                    self.log(f"✅ Synced {len(new_ips)} new IPs to blacklist")
                else:
                    self.log("✅ Blacklist already in sync with OpenSnitch")

        except Exception as e:
            self.log(f"⚠️ Error syncing OpenSnitch blocks: {e}")

    def run(self) -> None:
        self.log("=== Container Security Monitor with DNS Honeypot Started ===")
        self.log("Monitoring OpenSnitch blocks + DNS Honeypot queries + Direct TCP connections")

        # Setup cleanup handler (NOTE: iptables rules persist on exit)
        signal.signal(signal.SIGINT, lambda s, f: self._cleanup_and_exit())
        signal.signal(signal.SIGTERM, lambda s, f: self._cleanup_and_exit())

        self.update_container_mapping()

        # Add iptables rule for direct connection monitoring
        self.add_iptables_rule()

        try:
            conn = sqlite3.connect(OPENSNITCH_DB)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) FROM connections
                WHERE action = 'deny'
                AND time > datetime('now', '-5 minutes')
            """
            )
            recent_blocks = cursor.fetchone()[0]
            conn.close()
            self.log(f"📊 Found {recent_blocks} blocks in last 5 minutes")
        except Exception as e:
            self.log(f"⚠ Could not query OpenSnitch database: {e}")

        # Collection phase: Pre-warm DNS cache and detect past threats
        self.log("🚀 Starting collection phase...")
        self.collect_historical_data(hours=24)
        self.log("✅ Collection phase complete")

        # Sync all OpenSnitch blocks to blacklist AFTER DNS cache is warmed
        self.sync_opensnitch_blocks_to_blacklist()

        # Update mtime after sync to baseline for future change detection
        try:
            stat = os.stat(BLACKLIST_FILE)
            self.blacklist_mtime = stat.st_mtime
        except Exception:
            pass

        self.log("✅ Entering real-time monitoring...")

        # Now enable check_list_updates
        self.startup_complete = True

        threads = [
            threading.Thread(target=self.monitor_opensnitch, daemon=True),
            threading.Thread(target=self.monitor_honeypot, daemon=True),
            threading.Thread(target=self.monitor_direct_connections, daemon=True),
            threading.Thread(target=self.check_direct_connections, daemon=True),
            threading.Thread(target=self.periodic_tasks, daemon=True),
        ]

        for t in threads:
            t.start()

        self.log("✅ All monitoring threads started")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.log("\n=== Monitor stopped ===")
            self.log("Suspicious containers detected:")
            for container, count in sorted(self.suspect_containers.items(), key=lambda x: x[1], reverse=True):
                self.log(f"  {container}: {count} alerts")

    def _cleanup_and_exit(self) -> None:
        """Cleanup handler for signals (NOTE: iptables rules persist)"""
        self.log("\n=== Shutting down ===")
        self.log("ℹ️  iptables rules remain active (use --clear-iptables to remove)")
        self.log("Suspicious containers detected:")
        for container, count in sorted(self.suspect_containers.items(), key=lambda x: x[1], reverse=True):
            self.log(f"  {container}: {count} alerts")
        exit(0)


def clear_iptables_rules():
    """
    Clear all iptables rules created by this monitor.

    This removes:
    - The LOG rule for CONTAINER-TCP connections
    - All DROP rules for blacklisted IPs

    Usage:
        sudo python3 bin/docker_monitor.py --clear-iptables

    Use this when:
    - You want to stop monitoring and reduce log volume
    - You're troubleshooting network issues
    - You want to start fresh with iptables rules
    """
    print("🧹 Clearing iptables rules...")

    # Create monitor instance to reuse its methods
    monitor = ContainerMonitor()

    # 1. Remove LOG rule
    print("🔍 Removing LOG rule...")
    try:
        cmd = [
            "iptables",
            "-D",
            "DOCKER-USER",
            "-s",
            "172.0.0.0/8",
            "-p",
            "tcp",
            "-m",
            "conntrack",
            "--ctstate",
            "NEW",
            "-j",
            "LOG",
            "--log-prefix",
            "[CONTAINER-TCP] ",
            "--log-level",
            "4",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Removed LOG rule")
        else:
            print("ℹ️  LOG rule not found (already removed)")
    except Exception as e:
        print(f"⚠️ Failed to remove LOG rule: {e}")

    # 2. Remove all DROP rules for blacklisted IPs
    blacklisted = monitor._read_blacklist_file()
    if blacklisted:
        print(f"🔍 Removing {len(blacklisted)} DROP rules...")
        removed = 0
        for ip in blacklisted:
            try:
                cmd = ["iptables", "-D", "DOCKER-USER", "-s", "172.0.0.0/8", "-d", ip, "-j", "DROP"]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    removed += 1
            except Exception:
                pass
        print(f"✅ Removed {removed} DROP rules")
    else:
        print("ℹ️  No blacklisted IPs found")

    print("\n✅ iptables cleanup complete")
    print("ℹ️  Note: Blacklist file unchanged, only iptables rules removed")


def cleanup_blacklist():
    """
    Cleanup/Sweeping mode: Identify false positives using multi-source verification.

    This mode uses a hybrid approach with fallback logic to ensure maximum reliability:

    PRIMARY (when OpenSnitch available):
    1. Query OpenSnitch DB for all ARPA reverse DNS blocks (deny-always-arpa-53 rule)
    2. Extract IPs from blocked ARPA queries = confirmed threats (hardcoded IPs)
    3. Any blacklisted IP NOT in OpenSnitch blocks = false positive
    4. Cross-reference with DNS history for additional context

    FALLBACK (when OpenSnitch unavailable):
    1. Parse complete DNS honeypot history
    2. Build IP → domains mapping from DNS replies
    3. Any blacklisted IP with DNS history = likely false positive
    4. Conservative: require user confirmation before removal

    Usage:
        sudo python3 bin/docker_monitor.py --cleanup

    This hybrid approach:
    - Prioritizes OpenSnitch DB (persistent, reliable source of truth)
    - Falls back to DNS logs when OpenSnitch is unavailable
    - Provides migration path to pure iptables/journalctl monitoring
    """
    print("🧹 Cleanup mode: Analyzing blacklist for false positives...")

    # Create monitor instance to reuse its methods
    monitor = ContainerMonitor()

    # Read blacklist
    blacklisted = monitor._read_blacklist_file()
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
                ip = monitor.extract_ip_from_arpa(dst_host)
                if ip and monitor.is_valid_ip(ip) and not monitor.is_private_ip(ip):
                    opensnitch_blocked_ips.add(ip)

            print(f"✅ Found {len(opensnitch_blocked_ips)} IPs blocked by OpenSnitch (confirmed threats)")
            opensnitch_available = True

        except Exception as e:
            print(f"⚠️  OpenSnitch query failed: {e}")
            print("📋 Falling back to DNS log analysis...")

    # FALLBACK or SUPPLEMENTARY: Parse DNS logs
    print("🔍 SECONDARY: Parsing DNS logs from honeypot...")
    dns_cache = {}

    try:
        result = subprocess.run(["docker", "logs", HONEYPOT_CONTAINER], capture_output=True, text=True, timeout=30)
        dns_logs = result.stdout

        # Build IP → domains mapping from ALL reply lines
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
            exit(1)

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
                # Check DNS history for additional context
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
        print(f"   ✅ Source: OpenSnitch DB (PRIMARY - high confidence)")
    else:
        print(f"   ⚠️  Source: DNS logs only (FALLBACK - requires confirmation)")
    print(f"   False positives (move to whitelist): {len(to_whitelist)}")
    print(f"   Real threats (keep in blacklist): {len(to_keep)}")

    if to_whitelist:
        # Show more conservative prompt when using fallback
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
                f.write("# OpenSnitch blacklist - one IP per line\n")
                for ip in sorted(to_keep):
                    f.write(f"{ip}\n")

            print(f"✅ Moved {len(to_whitelist)} IPs to whitelist")
            print(f"✅ Kept {len(to_keep)} IPs in blacklist")
        else:
            print("❌ Cancelled")
    else:
        print("\n✅ No false positives found!")


if __name__ == "__main__":
    import sys

    if os.geteuid() != 0:
        print("Run as root: sudo python3 script.py")
        exit(1)

    # Check for command-line flags
    if len(sys.argv) > 1:
        if sys.argv[1] == "--cleanup":
            cleanup_blacklist()
            exit(0)
        elif sys.argv[1] == "--clear-iptables":
            clear_iptables_rules()
            exit(0)
        else:
            print(f"Unknown flag: {sys.argv[1]}")
            print("\nUsage:")
            print("  sudo python3 bin/docker_monitor.py                  # Normal monitoring")
            print("  sudo python3 bin/docker_monitor.py --cleanup        # Cleanup blacklist")
            print("  sudo python3 bin/docker_monitor.py --clear-iptables # Remove iptables rules")
            exit(1)

    if not os.path.exists(OPENSNITCH_DB):
        print(f"❌ Database not found: {OPENSNITCH_DB}")
        exit(1)

    try:
        with open(LOG_FILE, "a") as f:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            f.write(f"[{ts}] Started\n")
        print(f"✓ Log: {LOG_FILE}")
    except Exception as e:
        print(f"Failed to create log: {e}")
        exit(1)

    monitor = ContainerMonitor()
    monitor.run()
    monitor.run()
