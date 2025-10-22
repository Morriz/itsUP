"""Tests for monitor.opensnitch module"""
import unittest

from monitor.opensnitch import OpenSnitchIntegration


class TestOpenSnitchIntegration(unittest.TestCase):
    """Test OpenSnitch integration module"""

    def test_extract_ip_from_arpa(self):
        """Test ARPA reverse DNS IP extraction"""
        # Valid ARPA queries
        self.assertEqual(OpenSnitchIntegration.extract_ip_from_arpa("81.10.148.45.in-addr.arpa"), "45.148.10.81")
        self.assertEqual(OpenSnitchIntegration.extract_ip_from_arpa("8.8.8.8.in-addr.arpa"), "8.8.8.8")
        self.assertEqual(OpenSnitchIntegration.extract_ip_from_arpa("1.1.1.1.in-addr.arpa"), "1.1.1.1")

        # Invalid ARPA queries
        self.assertIsNone(OpenSnitchIntegration.extract_ip_from_arpa("not-arpa-query"))
        self.assertIsNone(OpenSnitchIntegration.extract_ip_from_arpa("example.com"))
        self.assertIsNone(OpenSnitchIntegration.extract_ip_from_arpa(""))


if __name__ == "__main__":
    unittest.main()
