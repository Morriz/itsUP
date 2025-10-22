"""Tests for monitor.core module - Core business logic only"""
import os
import re
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from monitor.core import ContainerMonitor


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


if __name__ == "__main__":
    unittest.main()
