# Generated by CodiumAI
import os
import sys
import unittest
from unittest import TestCase, mock
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.certs import get_certs


# pylint: disable=duplicate-code
@mock.patch("os.environ", {"LETSENCRYPT_EMAIL": "mail@example.com"})
class TestCodeUnderTest(TestCase):

    # Certbot command is run for each domain
    @mock.patch("lib.certs.get_domains", return_value=["example.com"])
    @mock.patch("lib.certs.run_command")
    def test_certbot_command_run_for_each_domain(self, mock_run_command: Mock, _: Mock) -> None:
        # Call the function under test
        get_certs()

        expected_command_calls = [
            mock.call(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--name",
                    "certbot",
                    "-v",
                    "./data:/data",
                    "-v",
                    "./certs:/certs",
                    "certbot/certbot",
                    "certonly",
                    "-d",
                    "example.com",
                    "--webroot",
                    "--webroot-path=/data/certbot",
                    "--email",
                    "mail@example.com",
                    "--agree-tos",
                    "--no-eff-email",
                    "--non-interactive",
                    "--config-dir",
                    "/data/letsencrypt",
                    "--work-dir",
                    "/data/letsencrypt",
                    "--logs-dir",
                    "/data/letsencrypt",
                    "--post-hook",
                    "mkdir -p /certs/example.com && \
                cp -L /data/letsencrypt/live/example.com/fullchain.pem /certs/example.com/fullchain.pem && \
                cp -L /data/letsencrypt/live/example.com/privkey.pem /certs/example.com/privkey.pem && \
                chown -R 101:101 /certs/example.com && touch /data/changed && chmod a+wr /data/changed",
                ],
            ),
        ]

        mock_run_command.assert_has_calls(expected_command_calls)

    # Certificates are updated if they have changed
    @mock.patch("lib.certs.get_domains", return_value=["example.com"])
    @mock.patch("lib.certs.run_command")
    @mock.patch("os.path.isfile")
    @mock.patch("os.remove")
    def test_certificates_updated_if_changed(
        self,
        mock_remove: Mock,
        mock_isfile: Mock,
        _1: Mock,
        _2: Mock,
    ) -> None:
        mock_isfile.return_value = True

        # Call the function under test
        result = get_certs()

        mock_remove.assert_called_once_with("./data/changed")
        self.assertTrue(result)

    # No domains are passed to certbot
    @mock.patch("lib.certs.run_command")
    @mock.patch("lib.certs.get_domains", return_value=[])
    @mock.patch("os.remove")
    def test_no_domains_passed_to_certbot(self, mock_remove: Mock, _: Mock, mock_run_command: Mock) -> None:
        # Call the function under test
        result = get_certs()

        mock_run_command.assert_not_called()
        mock_remove.assert_not_called()
        self.assertFalse(result)

    # LETSENCRYPT_EMAIL environment variable is not set
    @mock.patch("lib.certs.get_domains", return_value=[])
    @mock.patch("os.getenv", return_value=None)
    def test_le_email_env_variable_not_set(self, _1: Mock, _2: Mock) -> None:

        # Call the function under test
        with self.assertRaises(ValueError) as context:
            get_certs()

        self.assertEqual(str(context.exception), "LETSENCRYPT_EMAIL environment variable is not set")


if __name__ == "__main__":
    unittest.main()
