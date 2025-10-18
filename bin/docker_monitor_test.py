import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from docker_monitor import ContainerMonitor


class TestContainerMonitor(unittest.TestCase):

    def setUp(self):
        # Create temp files for blacklist/whitelist
        self.temp_blacklist = tempfile.NamedTemporaryFile(mode='w', delete=False)
        self.temp_whitelist = tempfile.NamedTemporaryFile(mode='w', delete=False)
        self.temp_log = tempfile.NamedTemporaryFile(mode='w', delete=False)

        # Write test data
        self.temp_blacklist.write("# Test blacklist\n")
        self.temp_blacklist.write("45.148.10.81\n")
        self.temp_blacklist.write("192.168.1.1\n")  # Private IP (should be filtered)
        self.temp_blacklist.close()

        self.temp_whitelist.write("# Test whitelist\n")
        self.temp_whitelist.write("8.8.8.8\n")
        self.temp_whitelist.close()

        self.temp_log.close()

        # Patch file paths
        self.patcher_blacklist = patch('docker_monitor.BLACKLIST_FILE', self.temp_blacklist.name)
        self.patcher_whitelist = patch('docker_monitor.WHITELIST_FILE', self.temp_whitelist.name)
        self.patcher_log = patch('docker_monitor.LOG_FILE', self.temp_log.name)

        # Mock iptables operations
        self.patcher_iptables_block = patch('docker_monitor.ContainerMonitor.block_ip_in_iptables')
        self.patcher_iptables_remove = patch('docker_monitor.ContainerMonitor.remove_ip_from_iptables')

        self.patcher_blacklist.start()
        self.patcher_whitelist.start()
        self.patcher_log.start()
        self.patcher_iptables_block.start()
        self.patcher_iptables_remove.start()

    def tearDown(self):
        self.patcher_blacklist.stop()
        self.patcher_whitelist.stop()
        self.patcher_log.stop()
        self.patcher_iptables_block.stop()
        self.patcher_iptables_remove.stop()

        os.unlink(self.temp_blacklist.name)
        os.unlink(self.temp_whitelist.name)
        os.unlink(self.temp_log.name)

    def test_is_valid_ip(self):
        monitor = ContainerMonitor()

        # Valid IPs
        self.assertTrue(monitor.is_valid_ip("192.168.1.1"))
        self.assertTrue(monitor.is_valid_ip("8.8.8.8"))
        self.assertTrue(monitor.is_valid_ip("255.255.255.255"))

        # Invalid IPs
        self.assertFalse(monitor.is_valid_ip("256.1.1.1"))
        self.assertFalse(monitor.is_valid_ip("192.168.1"))
        self.assertFalse(monitor.is_valid_ip("not.an.ip.address"))
        self.assertFalse(monitor.is_valid_ip("192.168.1.1.1"))

    def test_is_private_ip(self):
        monitor = ContainerMonitor()

        # Private IPs
        self.assertTrue(monitor.is_private_ip("10.0.0.1"))
        self.assertTrue(monitor.is_private_ip("172.16.0.1"))
        self.assertTrue(monitor.is_private_ip("172.31.255.255"))
        self.assertTrue(monitor.is_private_ip("192.168.1.1"))
        self.assertTrue(monitor.is_private_ip("127.0.0.1"))
        self.assertTrue(monitor.is_private_ip("169.254.1.1"))

        # Public IPs
        self.assertFalse(monitor.is_private_ip("8.8.8.8"))
        self.assertFalse(monitor.is_private_ip("1.1.1.1"))
        self.assertFalse(monitor.is_private_ip("172.15.0.1"))
        self.assertFalse(monitor.is_private_ip("172.32.0.1"))
        self.assertFalse(monitor.is_private_ip("45.148.10.81"))

    def test_extract_ip_from_arpa(self):
        monitor = ContainerMonitor()

        # Valid ARPA queries
        self.assertEqual(monitor.extract_ip_from_arpa("81.10.148.45.in-addr.arpa"), "45.148.10.81")
        self.assertEqual(monitor.extract_ip_from_arpa("8.8.8.8.in-addr.arpa"), "8.8.8.8")
        self.assertEqual(monitor.extract_ip_from_arpa("1.1.1.1.in-addr.arpa"), "1.1.1.1")

        # Invalid ARPA queries
        self.assertIsNone(monitor.extract_ip_from_arpa("not-arpa-query"))
        self.assertIsNone(monitor.extract_ip_from_arpa("example.com"))
        self.assertIsNone(monitor.extract_ip_from_arpa(""))

    def test_read_blacklist_file(self):
        monitor = ContainerMonitor()
        blacklist = monitor._read_blacklist_file()

        # Should contain non-comment, non-empty lines
        self.assertIn("45.148.10.81", blacklist)
        self.assertIn("192.168.1.1", blacklist)
        self.assertEqual(len(blacklist), 2)

    def test_load_blacklist_filters_comments(self):
        monitor = ContainerMonitor()

        # Blacklist should be loaded without comments
        self.assertIn("45.148.10.81", monitor.blacklisted_ips)
        self.assertIn("192.168.1.1", monitor.blacklisted_ips)

    def test_load_whitelist(self):
        monitor = ContainerMonitor()

        # Whitelist should be loaded
        self.assertIn("8.8.8.8", monitor.whitelisted_ips)

    def test_dns_cache_correlation(self):
        """Test DNS cache population and correlation logic"""
        monitor = ContainerMonitor()

        # Populate DNS cache
        now = datetime.now()
        monitor.dns_cache["45.148.10.81"] = [("malicious-c2.com", now)]
        monitor.dns_cache["1.1.1.1"] = [("cloudflare.com", now - timedelta(seconds=10))]

        # Test recent cache hit (within 5 seconds)
        self.assertIn("45.148.10.81", monitor.dns_cache)
        domains = [d for d, t in monitor.dns_cache["45.148.10.81"] if (now - t).total_seconds() <= 5]
        self.assertEqual(len(domains), 1)
        self.assertEqual(domains[0], "malicious-c2.com")

        # Test old cache miss (> 5 seconds)
        domains_old = [d for d, t in monitor.dns_cache["1.1.1.1"] if (now - t).total_seconds() <= 5]
        self.assertEqual(len(domains_old), 0)

    @patch('docker_monitor.ContainerMonitor.block_ip_in_iptables')
    def test_add_to_blacklist_atomic(self, mock_block):
        """Test atomic blacklist addition"""
        monitor = ContainerMonitor()
        initial_count = len(monitor._read_blacklist_file())

        # Add new IP
        monitor.add_to_blacklist("1.2.3.4", log_msg=False)

        # Verify added
        blacklist = monitor._read_blacklist_file()
        self.assertIn("1.2.3.4", blacklist)
        self.assertEqual(len(blacklist), initial_count + 1)

        # Try adding duplicate (should be no-op)
        monitor.add_to_blacklist("1.2.3.4", log_msg=False)
        blacklist = monitor._read_blacklist_file()
        self.assertEqual(len(blacklist), initial_count + 1)

        mock_block.assert_called()


if __name__ == "__main__":
    unittest.main()
