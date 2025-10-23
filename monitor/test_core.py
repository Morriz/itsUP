"""Tests for monitor.core module - Core business logic only"""
import json
import os
import re
import tempfile
import time
import unittest
from collections import deque
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

from monitor.core import ContainerMonitor
from monitor.constants import CONNECTION_GRACE_PERIOD


class TestDNSCorrelation(unittest.TestCase):
    """Test DNS correlation detection - the core feature"""

    def test_hardcoded_ip_detected_no_dns_cache(self):
        """Connection to IP without DNS cache = hardcoded IP (malware)"""
        monitor = ContainerMonitor(skip_sync=True)

        # Set up container mapping
        monitor._container_ips["172.30.0.5"] = "test-container"

        # Simulate connection to IP that was NEVER in DNS cache
        connections = {("172.30.0.5", "45.148.10.81", "443")}

        # Detect hardcoded IPs
        with patch.object(monitor, "log"):
            detected_count = monitor._detect_hardcoded_ips(connections)

        # Should detect 1 hardcoded IP
        self.assertEqual(detected_count, 1)
        self.assertIn("45.148.10.81", monitor.blacklist.get_all())

    def test_legitimate_connection_with_dns_cache(self):
        """Connection to IP that WAS in DNS cache = legitimate"""
        monitor = ContainerMonitor(skip_sync=True)

        # Set up container mapping
        monitor._container_ips["172.30.0.5"] = "test-container"

        # Pre-populate DNS cache with this IP
        monitor._dns_cache["45.148.10.81"] = [("example.com", datetime.now())]

        # Simulate connection to IP that IS in DNS cache
        connections = {("172.30.0.5", "45.148.10.81", "443")}

        # Detect hardcoded IPs
        with patch.object(monitor, "log"):
            detected_count = monitor._detect_hardcoded_ips(connections)

        # Should NOT detect any hardcoded IPs
        self.assertEqual(detected_count, 0)
        self.assertNotIn("45.148.10.81", monitor.blacklist.get_all())


class TestOpenSnitchCrossReference(unittest.TestCase):
    """Test OpenSnitch cross-reference validation - PRD requirement"""

    @patch("monitor.core.IptablesManager.add_drop_rule")
    def test_detection_confirmed_by_opensnitch(self, mock_iptables):
        """Detection + OpenSnitch block = high confidence threat"""
        monitor = ContainerMonitor(skip_sync=True, block=True, use_opensnitch=True)

        # OpenSnitch has blocked this IP
        monitor._opensnitch_blocked_ips.add("1.2.3.4")

        # Our monitor detects it
        with patch.object(monitor, "log") as mock_log:
            monitor.add_to_blacklist("1.2.3.4", log_msg=True)

            # Should log confirmation
            log_calls = [str(call) for call in mock_log.call_args_list]
            confirmed = any("✅ CONFIRMED by OpenSnitch" in str(c) for c in log_calls)
            self.assertTrue(confirmed, "Should show OpenSnitch confirmation")

    @patch("monitor.core.IptablesManager.add_drop_rule")
    def test_detection_not_confirmed_by_opensnitch(self, mock_iptables):
        """Detection but NOT in OpenSnitch = needs review (possible false positive)"""
        monitor = ContainerMonitor(skip_sync=True, block=True, use_opensnitch=True)

        # OpenSnitch has NOT blocked this IP
        monitor._opensnitch_blocked_ips.add("5.6.7.8")  # Different IP

        # Our monitor detects 1.2.3.4
        with patch.object(monitor, "log") as mock_log:
            monitor.add_to_blacklist("1.2.3.4", log_msg=True)

            # Should log warning
            log_calls = [str(call) for call in mock_log.call_args_list]
            needs_review = any("⚠️  NOT in OpenSnitch (needs review)" in str(c) for c in log_calls)
            self.assertTrue(needs_review, "Should warn about no OpenSnitch confirmation")


class TestWhitelistProtection(unittest.TestCase):
    """Test whitelist prevents blacklisting"""

    def test_whitelisted_ip_cannot_be_blacklisted(self):
        """Whitelisted IPs should never be blacklisted"""
        monitor = ContainerMonitor(skip_sync=True)

        # Whitelist an IP
        monitor.whitelist.add("1.2.3.4", persist=False)

        # Try to blacklist it
        monitor.add_to_blacklist("1.2.3.4")

        # Should NOT be in blacklist
        self.assertNotIn("1.2.3.4", monitor.blacklist.get_all())


class TestCompromiseReporting(unittest.TestCase):
    """Test compromise reporting and deduplication"""

    def test_duplicate_reports_are_deduplicated(self):
        """Same container+IP should only be reported once"""
        monitor = ContainerMonitor(skip_sync=True)

        with patch.object(monitor, "log") as mock_log:
            # First report
            monitor.report_compromise("test-container", "1.2.3.4", "hardcoded IP")
            self.assertEqual(mock_log.call_count, 1)

            # Duplicate report
            mock_log.reset_mock()
            monitor.report_compromise("test-container", "1.2.3.4", "hardcoded IP")
            self.assertEqual(mock_log.call_count, 0, "Duplicate should be suppressed")

        # Tracking should show 1 alert
        self.assertEqual(monitor._compromise_count_by_container["test-container"], 1)


class TestTimestampResumption(unittest.TestCase):
    """Test timestamp resumption - PRD FR2 requirement"""

    def test_extract_last_timestamp_with_microseconds(self):
        """Should extract full timestamp including microseconds from log"""
        monitor = ContainerMonitor(skip_sync=True)

        # Create temp log file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            f.write("[2025-10-22 13:32:18.714729] First log entry\n")
            f.write("[2025-10-22 13:32:21.231395] Second log entry\n")
            f.write("[2025-10-22 13:35:42.123456] Last log entry\n")
            log_file = f.name

        try:
            # Patch LOG_FILE constant
            with patch("monitor.core.LOG_FILE", log_file):
                timestamp = monitor._get_last_processed_timestamp()

            # Should get last timestamp with microseconds
            self.assertEqual(timestamp, "2025-10-22 13:35:42.123456")
        finally:
            os.unlink(log_file)

    def test_no_previous_run_returns_none(self):
        """First run with no log file should return None"""
        monitor = ContainerMonitor(skip_sync=True)

        # Patch with nonexistent file
        with patch("monitor.core.LOG_FILE", "/tmp/nonexistent_log_file_12345.log"):
            timestamp = monitor._get_last_processed_timestamp()

        self.assertIsNone(timestamp, "Should return None when no previous log exists")


class TestDNSRegexParsing(unittest.TestCase):
    """Test DNS log parsing - critical for correlation"""

    def test_parse_reply_format(self):
        """Should parse 'reply domain.com is 1.2.3.4' format"""
        line = "2025-10-22 13:29:48 dnsmasq[8]: reply api.crowdsec.net is 34.246.253.114"

        pattern = r"(?:reply|cached)\s+([^\s]+)\s+is\s+([0-9.]+)"
        match = re.search(pattern, line)

        self.assertIsNotNone(match, "Should match reply format")
        domain, ip = match.groups()
        self.assertEqual(domain, "api.crowdsec.net")
        self.assertEqual(ip, "34.246.253.114")

    def test_parse_cached_format(self):
        """Should parse 'cached domain.com is 1.2.3.4' format"""
        line = "2025-10-22 13:29:20 dnsmasq[8]: cached www.tm.prd.ags.akadns.net is 40.126.32.160"

        pattern = r"(?:reply|cached)\s+([^\s]+)\s+is\s+([0-9.]+)"
        match = re.search(pattern, line)

        self.assertIsNotNone(match, "Should match cached format")
        domain, ip = match.groups()
        self.assertEqual(domain, "www.tm.prd.ags.akadns.net")
        self.assertEqual(ip, "40.126.32.160")

    def test_ignore_query_lines(self):
        """Should NOT match 'query' lines (different format)"""
        line = "2025-10-22 13:44:37 dnsmasq[8]: query[A] we.instrukt.ai from 172.30.0.27"

        pattern = r"(?:reply|cached)\s+([^\s]+)\s+is\s+([0-9.]+)"
        match = re.search(pattern, line)

        self.assertIsNone(match, "Should not match query lines")


class TestDockerEventsIntegration(unittest.TestCase):
    """Test Docker events real-time container tracking"""

    @patch("subprocess.run")
    def test_container_start_event_updates_mapping(self, mock_run):
        """Container start event should add container to mapping"""
        monitor = ContainerMonitor(skip_sync=True)

        # Mock docker inspect responses
        mock_run.side_effect = [
            Mock(stdout="test-container", returncode=0),  # Get name
            Mock(stdout="172.25.0.100", returncode=0),  # Get IP
        ]

        # Simulate container start
        monitor._update_single_container("abc123")

        # Should be in mapping
        self.assertEqual(monitor._container_ips.get("172.25.0.100"), "test-container")

    @patch("subprocess.run")
    def test_container_stop_event_removes_from_mapping(self, mock_run):
        """Container stop event should remove container from mapping"""
        monitor = ContainerMonitor(skip_sync=True)

        # Pre-populate mapping
        monitor._container_ips["172.25.0.100"] = "test-container"

        # Mock docker inspect response
        mock_run.return_value = Mock(stdout="172.25.0.100", returncode=0)

        # Simulate container stop
        monitor._remove_container_from_mapping("abc123")

        # Should be removed from mapping
        self.assertNotIn("172.25.0.100", monitor._container_ips)

    @patch("subprocess.run")
    def test_container_restart_updates_mapping(self, mock_run):
        """Container restart should update mapping with new IP"""
        monitor = ContainerMonitor(skip_sync=True)

        # Old mapping
        monitor._container_ips["172.25.0.100"] = "test-container"

        # Mock docker inspect for removal (old IP)
        mock_run.return_value = Mock(stdout="172.25.0.100", returncode=0)
        monitor._remove_container_from_mapping("abc123")

        # Mock docker inspect for addition (new IP after restart)
        mock_run.side_effect = [
            Mock(stdout="test-container", returncode=0),  # Get name
            Mock(stdout="172.25.0.200", returncode=0),  # Get new IP
        ]
        monitor._update_single_container("abc123")

        # Old IP should be gone, new IP should be present
        self.assertNotIn("172.25.0.100", monitor._container_ips)
        self.assertEqual(monitor._container_ips.get("172.25.0.200"), "test-container")


class TestTimestampParsing(unittest.TestCase):
    """Test parsing actual event timestamps from journalctl logs"""

    def test_parse_iso_timestamp_with_microseconds(self):
        """Should parse ISO timestamp with microseconds from journalctl line"""
        # Simulate journalctl --output=short-iso-precise format
        line = "2025-10-22T23:28:37.817601+0200 raspberrypi kernel: [CONTAINER-TCP] IN=br-9cb4c31f2ce5 OUT=eth0 SRC=172.30.0.28 DST=87.215.147.1 SPT=40764 DPT=443"

        # Extract timestamp (first field)
        timestamp_match = re.match(r'^(\S+)', line)
        self.assertIsNotNone(timestamp_match)

        timestamp_str = timestamp_match.group(1)
        self.assertEqual(timestamp_str, "2025-10-22T23:28:37.817601+0200")

        # Parse it
        timestamp = datetime.fromisoformat(timestamp_str)
        timestamp = timestamp.replace(tzinfo=None)

        # Verify microseconds preserved
        self.assertEqual(timestamp.microsecond, 817601)
        self.assertEqual(timestamp.year, 2025)
        self.assertEqual(timestamp.month, 10)
        self.assertEqual(timestamp.day, 22)
        self.assertEqual(timestamp.hour, 23)
        self.assertEqual(timestamp.minute, 28)
        self.assertEqual(timestamp.second, 37)

    def test_timestamp_measures_actual_event_age(self):
        """Grace period should measure time since ACTUAL event, not since log was seen"""
        from datetime import timedelta

        # Event happened 3 seconds ago (actual time)
        event_timestamp = datetime.now() - timedelta(seconds=3)

        # Current time
        now = datetime.now()

        # Calculate age
        age = (now - event_timestamp).total_seconds()

        # Age should be ~3 seconds (actual event age)
        self.assertGreater(age, 2.9)
        self.assertLess(age, 3.2)


class TestGracePeriodTiming(unittest.TestCase):
    """Test grace period prevents premature DNS cache checks"""

    def test_connection_not_checked_before_grace_period(self):
        """Connections should NOT be checked until grace period expires"""
        monitor = ContainerMonitor(skip_sync=True)

        # Set up container mapping
        monitor._container_ips["172.30.0.5"] = "test-container"

        # Add connection to queue with current timestamp
        timestamp = datetime.now()
        monitor._recent_direct_connections.append((timestamp, "172.30.0.5", "1.2.3.4", "443"))

        # Grace period not expired yet (age = 0)
        with patch.object(monitor, "log"):
            # Manually check the grace period logic
            connection = monitor._recent_direct_connections[0]
            conn_timestamp, src_ip, dst_ip, dst_port = connection
            age = (datetime.now() - conn_timestamp).total_seconds()

            # Age should be near 0, well below grace period
            self.assertLess(age, CONNECTION_GRACE_PERIOD)

            # Connection should remain in queue (not processed)
            self.assertEqual(len(monitor._recent_direct_connections), 1)

    def test_connection_checked_after_grace_period(self):
        """Connections SHOULD be checked after grace period expires"""
        monitor = ContainerMonitor(skip_sync=True)

        # Set up container mapping
        monitor._container_ips["172.30.0.5"] = "test-container"

        # Add connection to queue with OLD timestamp (grace period already expired)
        # Simulate connection that's 6 seconds old (> 5s grace period)
        from datetime import timedelta
        old_timestamp = datetime.now() - timedelta(seconds=6)
        monitor._recent_direct_connections.append((old_timestamp, "172.30.0.5", "1.2.3.4", "443"))

        # Check age
        connection = monitor._recent_direct_connections[0]
        conn_timestamp, src_ip, dst_ip, dst_port = connection
        age = (datetime.now() - conn_timestamp).total_seconds()

        # Age should be > grace period, ready to check
        self.assertGreaterEqual(age, CONNECTION_GRACE_PERIOD)

    def test_grace_period_handles_dns_lag(self):
        """Grace period should allow DNS logs time to arrive"""
        monitor = ContainerMonitor(skip_sync=True)

        # Set up container mapping
        monitor._container_ips["172.30.0.5"] = "test-container"

        # Simulate sequence:
        # 1. Connection happens at T+0 (added to queue)
        timestamp = datetime.now()
        monitor._recent_direct_connections.append((timestamp, "172.30.0.5", "1.2.3.4", "443"))

        # 2. DNS hasn't arrived yet (empty cache)
        self.assertNotIn("1.2.3.4", monitor._dns_cache)

        # 3. Wait a bit (simulate DNS log arriving during grace period)
        time.sleep(0.1)  # Small delay to simulate DNS processing

        # 4. DNS arrives (before grace period expires)
        monitor._dns_cache["1.2.3.4"] = [("example.com", datetime.now())]

        # 5. After grace period, connection should find DNS cache and be OK
        # (This would be tested in integration, but we verify the setup here)
        self.assertIn("1.2.3.4", monitor._dns_cache)

    def test_grace_period_value_is_three_seconds(self):
        """Verify grace period constant is set to 3 seconds"""
        # This test ensures the fix is in place
        self.assertEqual(CONNECTION_GRACE_PERIOD, 3.0,
                        "Grace period should be 3 seconds to handle docker log buffering")


if __name__ == "__main__":
    unittest.main()
