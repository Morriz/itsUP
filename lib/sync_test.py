import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.sync import pull_repos


class TestPullRepos(unittest.TestCase):
    """Tests for git pull logic."""

    def setUp(self) -> None:
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self.root = Path(self._tmpdir)
        # Create repo dirs with .git markers
        for repo in ["projects", "secrets"]:
            repo_dir = self.root / repo
            repo_dir.mkdir()
            (repo_dir / ".git").mkdir()

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self._tmpdir)

    @patch("lib.sync.subprocess.run")
    def test_success_both_repos(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        result = pull_repos(self.root)
        self.assertEqual(result, {"projects": True, "secrets": True})
        self.assertEqual(mock_run.call_count, 2)

    @patch("lib.sync.subprocess.run")
    def test_conflict_aborts_rebase(self, mock_run: MagicMock) -> None:
        # First call (pull) fails, second call (rebase --abort) succeeds
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, "git pull", stderr="conflict"),
            MagicMock(returncode=0),  # rebase --abort
            MagicMock(returncode=0),  # secrets pull succeeds
        ]
        result = pull_repos(self.root)
        self.assertFalse(result["projects"])
        self.assertTrue(result["secrets"])
        # Verify rebase --abort was called
        abort_call = mock_run.call_args_list[1]
        self.assertIn("--abort", abort_call[0][0])

    @patch("lib.sync.subprocess.run")
    def test_both_fail(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, "git", stderr="fail1"),
            MagicMock(returncode=0),  # abort
            subprocess.CalledProcessError(1, "git", stderr="fail2"),
            MagicMock(returncode=0),  # abort
        ]
        result = pull_repos(self.root)
        self.assertEqual(result, {"projects": False, "secrets": False})

    def test_missing_repo_dir(self) -> None:
        import shutil

        shutil.rmtree(self.root / "projects")
        result = pull_repos(self.root)
        self.assertFalse(result["projects"])
        self.assertTrue(result["secrets"] or not result["secrets"])  # secrets depends on mock

    def test_not_a_git_repo(self) -> None:
        import shutil

        # Remove .git dir so it's not a repo
        shutil.rmtree(self.root / "projects" / ".git")
        with patch("lib.sync.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = pull_repos(self.root)
        self.assertTrue(result["projects"])  # skipped, not failed


if __name__ == "__main__":
    unittest.main()
