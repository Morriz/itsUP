#!/usr/bin/env python3
import sqlite3
import subprocess
import re
import time
import os
import signal
import atexit
from datetime import datetime, timedelta
from collections import defaultdict, deque
import threading

LOG_FILE = "/var/log/compromised_container.log"
OPENSNITCH_DB = os.getenv("OPENSNITCH_DB", "/var/lib/opensnitch/opensnitch.sqlite3")
HONEYPOT_CONTAINER = "dns-honeypot"
BLACKLIST_FILE = "/etc/opensnitchd/blacklists/blacklist-outbound-ips.txt"
WHITELIST_FILE = "/etc/opensnitchd/whitelists/whitelist-outbound-ips.txt"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")  # DEBUG or INFO

class ContainerMonitor:
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
        """Load whitelisted IPs from file"""
        try:
            import os
            stat = os.stat(WHITELIST_FILE)
            self.whitelist_mtime = stat.st_mtime

            new_whitelist = set()
            with open(WHITELIST_FILE, "r") as f:
                for line in f:
                    ip = line.strip()
                    if ip and not ip.startswith("#"):
                        new_whitelist.add(ip)

            with self.lock:
                self.whitelisted_ips = new_whitelist

            if new_whitelist:
                self.log(f"📋 Loaded {len(new_whitelist)} IPs from whitelist")

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
        pattern = r'(\d+)\.(\d+)\.(\d+)\.(\d+)\.in-addr\.arpa'
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
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.ID}} {{.Names}}"],
            capture_output=True,
            text=True
        )

        new_mapping = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                cid, cname = parts

                inspect = subprocess.run(
                    ["docker", "inspect", "-f",
                     "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}", cid],
                    capture_output=True,
                    text=True
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
            ['docker', 'logs', '-f', '--tail', '0', HONEYPOT_CONTAINER],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Pattern: 2025-10-17 12:44:05. dnsmasq[17]: query[PTR] 89.10.148.45.in-addr.arpa from 172.30.0.28
        query_pattern = re.compile(
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+ dnsmasq\[\d+\]: query\[(\w+)\] ([\w\.\-]+) from ([\d\.]+)'
        )
        # Pattern: 2025-10-17 12:44:05 dnsmasq[11]: reply registry.npmjs.org is 104.16.3.35
        reply_pattern = re.compile(
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+dnsmasq\[\d+\]: reply ([\w\.\-]+) is ([\d\.]+)'
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
                    if 'in-addr.arpa' in query_domain:
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
                                    self.honeypot_queries.append((timestamp, query_domain, source_ip, container_name, queried_ip))

                                # Check if OpenSnitch blocked it
                                self.correlate_honeypot_with_opensnitch(timestamp, query_domain, container_name, queried_ip)

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

            cursor.execute("""
                SELECT time, action, dst_host, process
                FROM connections
                WHERE dst_host = ?
                AND time BETWEEN ? AND ?
                ORDER BY time ASC
                LIMIT 1
            """, (query_domain, time_min, time_max))

            row = cursor.fetchone()
            conn.close()

            if row:
                block_time, action, dst_host, process = row
                if action == 'deny':
                    self.log(f"🍯 Reverse DNS: {container_name} queried {query_domain} → {malware_ip} ⚠️ BLOCKED! 🚨", "INFO")
                    self.add_to_blacklist(malware_ip)
                    self.report_compromise(
                        container_name,
                        malware_ip,
                        f"honeypot logged query, OpenSnitch blocked via {process}"
                    )
            else:
                self.log(f"🍯 Reverse DNS: {container_name} queried {query_domain} → {malware_ip}", "DEBUG")
        except Exception as e:
            self.log(f"Correlation error: {e}")

    def add_iptables_rule(self) -> None:
        """Add iptables rule to log all container TCP traffic (filter private IPs in Python)"""
        try:
            cmd = [
                "iptables", "-I", "DOCKER-USER", "1",
                "-s", "172.0.0.0/8",
                "-p", "tcp",
                "-j", "LOG",
                "--log-prefix", "[CONTAINER-TCP] ",
                "--log-level", "4"
            ]
            subprocess.run(cmd, check=True)
            self.iptables_rule_added = True
            self.log("✅ Added iptables rule for container TCP monitoring (filtering private IPs in Python)")
        except Exception as e:
            self.log(f"❌ Failed to add iptables rule: {e}")

    def block_ip_in_iptables(self, ip: str, log: bool = True) -> None:
        """Add iptables DROP rule for blacklisted IP"""
        try:
            # Add rule to DROP traffic to this IP (before the LOG rule)
            cmd = [
                "iptables", "-I", "DOCKER-USER", "1",
                "-s", "172.0.0.0/8",
                "-d", ip,
                "-j", "DROP"
            ]
            subprocess.run(cmd, check=True)
            if log:
                self.log(f"🚫 Blocked {ip} in iptables")
        except Exception as e:
            self.log(f"❌ Failed to block {ip} in iptables: {e}")

    def remove_ip_from_iptables(self, ip: str) -> None:
        """Remove iptables DROP rule for IP"""
        try:
            cmd = [
                "iptables", "-D", "DOCKER-USER",
                "-s", "172.0.0.0/8",
                "-d", ip,
                "-j", "DROP"
            ]
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
                "iptables", "-D", "DOCKER-USER",
                "-s", "172.0.0.0/8",
                "-p", "tcp",
                "-j", "LOG",
                "--log-prefix", "[CONTAINER-TCP] ",
                "--log-level", "4"
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
            bufsize=1
        )

        pattern = re.compile(r'\[CONTAINER-TCP\].*SRC=([0-9.]+).*DST=([0-9.]+).*DPT=([0-9]+)')

        try:
            for line in iter(proc.stdout.readline, ''):
                if not line:
                    break
                match = pattern.search(line)
                if match:
                    src_ip, dst_ip, dst_port = match.groups()

                    # Filter out private IPs (only track external connections)
                    if self.is_private_ip(dst_ip):
                        continue

                    # Skip whitelisted IPs
                    with self.lock:
                        if dst_ip in self.whitelisted_ips:
                            continue

                    timestamp = datetime.now()
                    conn_key = (src_ip, dst_ip, int(dst_port))

                    # Deduplicate - only store unique connections (not every packet)
                    with self.lock:
                        last_seen = self.seen_direct_connections.get(conn_key)

                        # Only store if new or not seen in last 30 seconds
                        if not last_seen or (timestamp - last_seen).total_seconds() > 30:
                            self.seen_direct_connections[conn_key] = timestamp
                            self.recent_direct_connections.append((timestamp, src_ip, dst_ip, int(dst_port)))

                            # Don't log here - will log only when checking correlation

        except KeyboardInterrupt:
            proc.terminate()
        except Exception as e:
            self.log(f"❌ Direct connection monitor error: {e}")
        finally:
            proc.terminate()

    def check_direct_connections(self) -> None:
        """Periodically log recent direct connections"""
        while True:
            time.sleep(2)

            with self.lock:
                if not self.recent_direct_connections:
                    continue

                # Copy to avoid holding lock
                connections = list(self.recent_direct_connections)

            try:
                for timestamp, src_ip, dst_ip, dst_port in connections:
                    container_name = self.get_container_from_ip(src_ip)

                    if container_name:
                        # Just log it - OpenSnitch can't block container traffic
                        self.log(f"🌐 Direct IP: {container_name} → {dst_ip}:{dst_port}", "DEBUG")

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
                max_time = cursor.fetchone()[0]

                cursor.execute("""
                    SELECT time, dst_host, dst_ip, dst_port, protocol, process
                    FROM connections
                    WHERE time > ?
                    AND rule = 'deny-always-arpa-53'
                    ORDER BY time ASC
                """, (last_time,))

                rows = cursor.fetchall()
                conn.close()

                for row in rows:
                    timestamp, dst_host, dst_ip, dst_port, protocol, process = row
                    last_time = timestamp

                    # ONLY process ARPA reverse DNS blocks
                    if dst_host and 'in-addr.arpa' in dst_host:
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
                                            self.log(f"📋 Host reverse DNS for {ip} (container queried: {domain}) - FALSE POSITIVE", "INFO")
                                            # Add to whitelist instead of blacklist
                                            with open(WHITELIST_FILE, "a") as f:
                                                f.write(f"{ip}\n")
                                            self.whitelisted_ips.add(ip)
                                            break

                            if not found_in_cache:
                                # NO forward DNS seen - hardcoded IP - real threat!
                                self.log(f"📋 Host reverse DNS for {ip} - NO container forward query (HARDCODED IP - MALWARE!) 🚨", "INFO")
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
                self.honeypot_queries = [
                    q for q in self.honeypot_queries if q[0] > cutoff
                ]

                # Clean DNS cache (keep last 5 seconds only)
                dns_cutoff = datetime.now() - timedelta(seconds=5)
                new_dns_cache = {}
                for ip, entries in self.dns_cache.items():
                    recent = [(domain, ts) for domain, ts in entries if ts > dns_cutoff]
                    if recent:
                        new_dns_cache[ip] = recent
                self.dns_cache = new_dns_cache

                # Clean old direct connection tracking
                self.seen_direct_connections = {
                    k: v for k, v in self.seen_direct_connections.items()
                    if (datetime.now() - v).total_seconds() < 300
                }

            if int(time.time()) % 300 == 0:
                with self.lock:
                    if self.suspect_containers:
                        self.log("📊 Suspicious Activity Summary:")
                        for container, count in sorted(self.suspect_containers.items(),
                                                      key=lambda x: x[1], reverse=True):
                            self.log(f"   {container}: {count} suspicious connections")

            time.sleep(10)

    def sync_opensnitch_blocks_to_blacklist(self) -> None:
        """Sync ONLY ARPA reverse DNS blocked IPs to blacklist - ATOMIC"""
        try:
            conn = sqlite3.connect(OPENSNITCH_DB)
            cursor = conn.cursor()

            # Get ONLY reverse DNS (ARPA) blocks from deny-always-arpa-53 rule
            cursor.execute("""
                SELECT DISTINCT dst_host, dst_ip
                FROM connections
                WHERE rule = 'deny-always-arpa-53'
                AND dst_host LIKE '%.in-addr.arpa'
            """)

            rows = cursor.fetchall()
            conn.close()

            # Atomic operation - read file once, write once
            with self.blacklist_file_lock:
                existing_ips = self._read_blacklist_file()

                new_ips = []
                for dst_host, dst_ip in rows:
                    ip = None

                    # Extract IP from ARPA reverse DNS ONLY
                    if dst_host and 'in-addr.arpa' in dst_host:
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

        # Setup cleanup handler
        atexit.register(self.remove_iptables_rule)
        signal.signal(signal.SIGINT, lambda s, f: self._cleanup_and_exit())
        signal.signal(signal.SIGTERM, lambda s, f: self._cleanup_and_exit())

        self.update_container_mapping()

        # Add iptables rule for direct connection monitoring
        self.add_iptables_rule()

        try:
            conn = sqlite3.connect(OPENSNITCH_DB)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM connections
                WHERE action = 'deny'
                AND time > datetime('now', '-5 minutes')
            """)
            recent_blocks = cursor.fetchone()[0]
            conn.close()
            self.log(f"📊 Found {recent_blocks} blocks in last 5 minutes")
        except Exception as e:
            self.log(f"⚠ Could not query OpenSnitch database: {e}")

        # Sync all OpenSnitch blocks to blacklist on startup
        self.sync_opensnitch_blocks_to_blacklist()

        # Update mtime after sync to baseline for future change detection
        try:
            stat = os.stat(BLACKLIST_FILE)
            self.blacklist_mtime = stat.st_mtime
        except Exception:
            pass

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
            for container, count in sorted(self.suspect_containers.items(),
                                          key=lambda x: x[1], reverse=True):
                self.log(f"  {container}: {count} alerts")

    def _cleanup_and_exit(self) -> None:
        """Cleanup handler for signals"""
        self.log("\n=== Shutting down ===")
        self.remove_iptables_rule()
        self.log("Suspicious containers detected:")
        for container, count in sorted(self.suspect_containers.items(),
                                      key=lambda x: x[1], reverse=True):
            self.log(f"  {container}: {count} alerts")
        exit(0)

def cleanup_blacklist():
    """Cleanup mode: Check blacklist IPs against DNS history, move false positives to whitelist"""
    print("🧹 Cleanup mode: Analyzing blacklist against DNS history...")

    # Create monitor instance to reuse its methods
    monitor = ContainerMonitor()

    # Read blacklist
    blacklisted = monitor._read_blacklist_file()
    print(f"📋 Found {len(blacklisted)} IPs in blacklist")

    # Parse ALL DNS reply logs from honeypot
    print("🔍 Parsing DNS logs from honeypot...")
    try:
        result = subprocess.run(
            ['docker', 'logs', HONEYPOT_CONTAINER],
            capture_output=True,
            text=True,
            timeout=30
        )
        dns_logs = result.stdout
    except Exception as e:
        print(f"❌ Failed to get DNS logs: {e}")
        exit(1)

    # Build IP → domains mapping from ALL reply lines
    reply_pattern = re.compile(r'reply ([\w\.\-]+) is ([\d\.]+)')
    dns_cache = {}

    for line in dns_logs.split('\n'):
        match = reply_pattern.search(line)
        if match:
            domain, ip = match.groups()
            # Use existing validation methods
            if monitor.is_valid_ip(ip) and not monitor.is_private_ip(ip):
                if ip not in dns_cache:
                    dns_cache[ip] = set()
                dns_cache[ip].add(domain)

    print(f"🔍 Found {len(dns_cache)} unique IPs in DNS history")

    # Check each blacklisted IP
    to_whitelist = []
    to_keep = []

    for ip in blacklisted:
        if ip in dns_cache:
            domains = dns_cache[ip]
            print(f"✅ {ip} → {', '.join(sorted(domains)[:3])} (FALSE POSITIVE)")
            to_whitelist.append((ip, domains))
        else:
            print(f"🚨 {ip} → NO DNS history (KEEP IN BLACKLIST)")
            to_keep.append(ip)

    # Summary
    print(f"\n📊 Summary:")
    print(f"   False positives (move to whitelist): {len(to_whitelist)}")
    print(f"   Real threats (keep in blacklist): {len(to_keep)}")

    if to_whitelist:
        confirm = input(f"\n❓ Move {len(to_whitelist)} IPs to whitelist? [y/N]: ")
        if confirm.lower() == 'y':
            # Add to whitelist
            with open(WHITELIST_FILE, "a") as f:
                for ip, domains in to_whitelist:
                    f.write(f"{ip}  # {', '.join(sorted(domains)[:2])}\n")

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

    # Check for cleanup mode
    if len(sys.argv) > 1 and sys.argv[1] == '--cleanup':
        cleanup_blacklist()
        exit(0)

    if not os.path.exists(OPENSNITCH_DB):
        print(f"❌ Database not found: {OPENSNITCH_DB}")
        exit(1)

    try:
        with open(LOG_FILE, "a") as f:
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            f.write(f"[{ts}] Started\n")
        print(f"✓ Log: {LOG_FILE}")
    except Exception as e:
        print(f"Failed to create log: {e}")
        exit(1)

    monitor = ContainerMonitor()
    monitor.run()
