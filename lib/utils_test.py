import os
import subprocess
import sys
import unittest
from unittest import mock
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.utils import run_command, stream_output


class TestStreamOutput(unittest.TestCase):

    # Outputs the process stdout to sys.stdout.buffer.
    @mock.patch("subprocess.Popen")
    @mock.patch("sys.stdout.buffer.write")
    def test_outputs_stdout(self, mock_write: Mock, mock_popen: Mock) -> None:
        process = mock_popen.return_value
        process.stdout.read.side_effect = [b"output1", b"output2", b""]

        stream_output(process)

        mock_write.assert_has_calls([mock.call(b"output1"), mock.call(b"output2")])

    # Handles the process stdout stream correctly.
    @mock.patch("subprocess.Popen")
    @mock.patch("sys.stdout.buffer.write")
    def test_handles_stdout_stream(self, mock_write: Mock, mock_popen: Mock) -> None:
        process = mock_popen.return_value
        process.stdout.read.side_effect = [b"output1", b"output2", b""]

        stream_output(process)

        mock_write.assert_has_calls([mock.call(b"output1"), mock.call(b"output2")])


class TestRunCommand(unittest.TestCase):

    # Runs command with no errors and returns exit code
    @mock.patch("lib.utils.stream_output")
    @mock.patch("subprocess.Popen")
    def test_runs_command_no_errors(self, mock_popen: Mock, _: Mock) -> None:

        # Set up mock
        mock_process = mock_popen.return_value
        mock_process.returncode = 0

        # Call the function under test
        exit_code = run_command(["ls"])

        # Assert the exit code is returned correctly
        self.assertEqual(exit_code, 0)
        mock_popen.assert_called_once_with(["ls"], cwd=None, stdout=subprocess.PIPE)


if __name__ == "__main__":
    unittest.main()
