# Tests drive the reconciler's internal single-flight state directly.
# pylint: disable=protected-access
import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import lib.reconcile as reconcile_mod
from lib.reconcile import ReconcileError, reconcile


class TestReconcile(unittest.TestCase):
    """Tests for the single-flight, coalescing full-stack reconcile."""

    def setUp(self) -> None:
        reconcile_mod._reconciler._running = False
        reconcile_mod._reconciler._dirty = False

    @patch("lib.reconcile.subprocess.run")
    @patch("lib.reconcile.pull_repos")
    def test_pull_then_apply_success(self, mock_pull: MagicMock, mock_run: MagicMock) -> None:
        mock_pull.return_value = {"projects": True, "secrets": True}

        reconcile()

        mock_pull.assert_called_once()
        mock_run.assert_called_once()
        # `itsup apply` with no project arg = full-stack apply.
        cmd = mock_run.call_args[0][0]
        self.assertTrue(cmd[0].endswith(".venv/bin/itsup"))
        self.assertEqual(cmd[-1], "apply")
        self.assertFalse(reconcile_mod._reconciler._running)

    @patch("lib.reconcile.subprocess.run")
    @patch("lib.reconcile.pull_repos")
    def test_pull_failure_raises_and_skips_apply(self, mock_pull: MagicMock, mock_run: MagicMock) -> None:
        mock_pull.return_value = {"projects": True, "secrets": False}

        with self.assertRaises(ReconcileError):
            reconcile()

        mock_run.assert_not_called()
        self.assertFalse(reconcile_mod._reconciler._running)
        self.assertFalse(reconcile_mod._reconciler._dirty)

    @patch("lib.reconcile.pull_repos")
    def test_coalesces_when_already_running(self, mock_pull: MagicMock) -> None:
        # Simulate a reconcile already in flight on another thread.
        reconcile_mod._reconciler._running = True

        reconcile()

        self.assertTrue(reconcile_mod._reconciler._dirty)
        mock_pull.assert_not_called()

    @patch("lib.reconcile.subprocess.run")
    @patch("lib.reconcile.pull_repos")
    def test_dirty_during_run_triggers_one_trailing_run(self, mock_pull: MagicMock, mock_run: MagicMock) -> None:
        mock_pull.return_value = {"projects": True, "secrets": True}
        passes = {"n": 0}

        def trigger_mid_run(*_args: object, **_kwargs: object) -> MagicMock:
            passes["n"] += 1
            if passes["n"] == 1:
                # A webhook arrives while the first apply runs.
                reconcile_mod._reconciler._dirty = True
            return MagicMock()

        mock_run.side_effect = trigger_mid_run

        reconcile()

        self.assertEqual(mock_run.call_count, 2)
        self.assertFalse(reconcile_mod._reconciler._running)
        self.assertFalse(reconcile_mod._reconciler._dirty)

    @patch("lib.reconcile.subprocess.run")
    @patch("lib.reconcile.pull_repos")
    def test_apply_failure_resets_state(self, mock_pull: MagicMock, mock_run: MagicMock) -> None:
        mock_pull.return_value = {"projects": True, "secrets": True}
        mock_run.side_effect = subprocess.CalledProcessError(1, "itsup")

        with self.assertRaises(subprocess.CalledProcessError):
            reconcile()

        self.assertFalse(reconcile_mod._reconciler._running)
        self.assertFalse(reconcile_mod._reconciler._dirty)


if __name__ == "__main__":
    unittest.main()
