"""Tests for monitor.core module - Core business logic only"""

import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

from monitor.core import ContainerMonitor


class TestDNSCorrelation(unittest.TestCase):
    """Test DNS correlation detection - the core feature"""

    @patch("monitor.core.logger")
    def test_hardcoded_ip_detected_no_dns_cache(self, mock_logger: MagicMock) -> None:
        """Connection to IP without DNS cache = hardcoded IP (malware)"""
        monitor = ContainerMonitor(skip_sync=True)

        # Set up container mapping
        monitor._container_ips["172.30.0.5"] = "test-container"

        # Simulate connection to IP that was NEVER in DNS cache
        connections = {("172.30.0.5", "45.148.10.81", "443")}

        # Detect hardcoded IPs
        detected_count = monitor._detect_hardcoded_ips(connections)

        # Should detect 1 hardcoded IP
        self.assertEqual(detected_count, 1)
        self.assertIn("45.148.10.81", monitor.blacklist.get_all())

    @patch("monitor.core.logger")
    def test_legitimate_connection_with_dns_cache(self, mock_logger: MagicMock) -> None:
        """Connection to IP that WAS in DNS cache = legitimate"""
        monitor = ContainerMonitor(skip_sync=True)

        # Set up container mapping
        monitor._container_ips["172.30.0.5"] = "test-container"

        # Pre-populate DNS cache with this IP
        monitor._dns_cache["45.148.10.81"] = [("example.com", datetime.now())]

        # Simulate connection to IP that IS in DNS cache
        connections = {("172.30.0.5", "45.148.10.81", "443")}

        # Detect hardcoded IPs
        detected_count = monitor._detect_hardcoded_ips(connections)

        # Should NOT detect any hardcoded IPs
        self.assertEqual(detected_count, 0)
        self.assertNotIn("45.148.10.81", monitor.blacklist.get_all())


class TestVPNExclusion(unittest.TestCase):
    """Test VPN container exclusion from blacklist"""

    @patch("monitor.core.logger")
    def test_vpn_container_not_blacklisted(self, mock_logger: MagicMock) -> None:
        """VPN containers should be silently skipped (no blacklist, no reporting)"""
        monitor = ContainerMonitor(skip_sync=True)

        # Simulate VPN container detection
        monitor._handle_hardcoded_ip_detection("vpn-vpn-openvpn-server1", "1.2.3.4", "443", log_blacklist=True)

        # Should NOT be in blacklist
        self.assertNotIn("1.2.3.4", monitor.blacklist.get_all())

        # Should NOT be in reported compromises
        self.assertNotIn("vpn-vpn-openvpn-server1:1.2.3.4", monitor._reported_compromises)

        # Should only log at DEBUG level
        self.assertEqual(mock_logger.warning.call_count, 0, "Should not log warnings for VPN containers")

    @patch("monitor.core.IptablesManager.add_drop_rule")
    def test_non_vpn_container_is_blacklisted(self, _mock_iptables: MagicMock) -> None:
        """Non-VPN containers should be blacklisted and reported normally"""
        monitor = ContainerMonitor(skip_sync=True)

        # Simulate normal container detection
        monitor._handle_hardcoded_ip_detection("test-container", "1.2.3.4", "443", log_blacklist=True)

        # Behavior: the IP is blacklisted and the container+IP is reported
        self.assertIn("1.2.3.4", monitor.blacklist.get_all())
        self.assertIn("test-container:1.2.3.4", monitor._reported_compromises)

    @patch("monitor.core.logger")
    def test_vpn_exclusion_prefix_match(self, mock_logger: MagicMock) -> None:
        """VPN exclusion should match prefix 'vpn-vpn-openvpn-'"""
        monitor = ContainerMonitor(skip_sync=True)

        # Test various VPN container names
        vpn_names = [
            "vpn-vpn-openvpn-server1",
            "vpn-vpn-openvpn-client",
            "vpn-vpn-openvpn-test-123",
        ]

        for vpn_name in vpn_names:
            monitor._handle_hardcoded_ip_detection(vpn_name, f"1.2.3.{len(vpn_name)}", "443", log_blacklist=True)

        # None should be blacklisted or reported
        for i, vpn_name in enumerate(vpn_names):
            ip = f"1.2.3.{len(vpn_name)}"
            self.assertNotIn(ip, monitor.blacklist.get_all(), f"{vpn_name} should not be blacklisted")
            self.assertNotIn(f"{vpn_name}:{ip}", monitor._reported_compromises, f"{vpn_name} should not be reported")

        # Should not log warnings (only DEBUG)
        self.assertEqual(mock_logger.warning.call_count, 0, "Should not log warnings for VPN containers")


class TestWhitelistProtection(unittest.TestCase):
    """Test whitelist prevents blacklisting"""

    def test_whitelisted_ip_cannot_be_blacklisted(self) -> None:
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

    @patch("monitor.core.logger")
    def test_duplicate_reports_are_deduplicated(self, mock_logger: MagicMock) -> None:
        """Same container+IP should only be reported once"""
        monitor = ContainerMonitor(skip_sync=True)

        # First report
        monitor.report_compromise("test-container", "1.2.3.4", "hardcoded IP")
        self.assertEqual(mock_logger.warning.call_count, 1)

        # Duplicate report
        mock_logger.reset_mock()
        monitor.report_compromise("test-container", "1.2.3.4", "hardcoded IP")
        self.assertEqual(mock_logger.warning.call_count, 0, "Duplicate should be suppressed")

        # Tracking should show 1 alert
        self.assertEqual(monitor._compromise_count_by_container["test-container"], 1)


class TestTimestampResumption(unittest.TestCase):
    """Test timestamp resumption - PRD FR2 requirement"""

    def test_extract_last_timestamp_with_microseconds(self) -> None:
        """Should extract full timestamp including microseconds from log"""
        monitor = ContainerMonitor(skip_sync=True)

        # Create temp log file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
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

    def test_no_previous_run_returns_none(self) -> None:
        """First run with no log file should return None"""
        monitor = ContainerMonitor(skip_sync=True)

        # Patch with nonexistent file
        with patch("monitor.core.LOG_FILE", "/tmp/nonexistent_log_file_12345.log"):
            timestamp = monitor._get_last_processed_timestamp()

        self.assertIsNone(timestamp, "Should return None when no previous log exists")


class TestDockerEventsIntegration(unittest.TestCase):
    """Test Docker events real-time container tracking"""

    @patch("subprocess.run")
    def test_container_start_event_updates_mapping(self, mock_run: MagicMock) -> None:
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
    def test_container_stop_event_removes_from_mapping(self, mock_run: MagicMock) -> None:
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
    def test_container_restart_updates_mapping(self, mock_run: MagicMock) -> None:
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
