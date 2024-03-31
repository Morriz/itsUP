import os
import sys
import unittest
from unittest import mock
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.utils import run_command


class TestRunCommand(unittest.TestCase):

    # Runs command with no errors and returns exit code
    @mock.patch("builtins.open", new_callable=mock.mock_open)
    @mock.patch("subprocess.run")
    def test_runs_command_no_errors(self, mock_run: Mock, mock_open: Mock) -> None:

        # Set up mock
        mock_process = mock_run.return_value
        mock_process.returncode = 0

        # Call the function under test
        exit_code = run_command(["ls"])

        # Assert the exit code is returned correctly
        self.assertEqual(exit_code, 0)
        # Assert the open call was made correctly
        mock_open.assert_called_with("logs/error.log", "w", encoding="utf-8")
        # Assert the subprocess.run call was made correctly
        mock_run.assert_called_once_with(
            ["ls"], check=True, cwd=None, env={}, stdout=mock_open.return_value, stderr=mock_open.return_value
        )


if __name__ == "__main__":
    unittest.main()
