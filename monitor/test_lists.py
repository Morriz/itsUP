"""Tests for monitor.lists module"""
import os
import tempfile
import threading
import unittest

from monitor.lists import IPList


class TestIPList(unittest.TestCase):
    """Test IPList file management"""

    def setUp(self):
        """Setup test fixtures"""
        self.temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False)
        self.temp_file.write("# Test list\n")
        self.temp_file.write("1.2.3.4\n")
        self.temp_file.write("5.6.7.8\n")
        self.temp_file.close()

    def tearDown(self):
        """Cleanup test fixtures"""
        os.unlink(self.temp_file.name)

    def test_loading(self):
        """Test loading IPs from file"""

        def mock_log(msg, level="INFO"):
            pass

        iplist = IPList(self.temp_file.name, mock_log, threading.Lock())
        iplist.load()

        # Should load both IPs
        self.assertIn("1.2.3.4", iplist.get_all())
        self.assertIn("5.6.7.8", iplist.get_all())
        self.assertEqual(len(iplist.get_all()), 2)

    def test_adding(self):
        """Test adding IPs to list"""

        def mock_log(msg, level="INFO"):
            pass

        iplist = IPList(self.temp_file.name, mock_log, threading.Lock())
        iplist.load()

        # Add new IP
        added = iplist.add("9.10.11.12", persist=False)
        self.assertTrue(added)
        self.assertIn("9.10.11.12", iplist.get_all())

        # Try adding duplicate
        added = iplist.add("9.10.11.12", persist=False)
        self.assertFalse(added)

    def test_contains(self):
        """Test IP membership check"""

        def mock_log(msg, level="INFO"):
            pass

        iplist = IPList(self.temp_file.name, mock_log, threading.Lock())
        iplist.load()

        self.assertTrue(iplist.contains("1.2.3.4"))
        self.assertFalse(iplist.contains("99.99.99.99"))


if __name__ == "__main__":
    unittest.main()
