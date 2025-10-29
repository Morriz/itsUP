#!/usr/bin/env python3

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from commands.commit import _has_changes


class TestCommitCommand(unittest.TestCase):
    """Tests for commit command"""

    def test_has_changes_with_changes(self) -> None:
        """Test _has_changes returns True when repo has changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="M file.txt\n")

                result = _has_changes(repo_path)

                self.assertTrue(result)
                mock_run.assert_called_once()

    def test_has_changes_without_changes(self) -> None:
        """Test _has_changes returns False when repo is clean."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="")

                result = _has_changes(repo_path)

                self.assertFalse(result)

    def test_has_changes_git_error(self) -> None:
        """Test _has_changes returns False on git error."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")):
                result = _has_changes(repo_path)

                self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
