"""Full-stack reconcile: pull the config repos, then apply.

Triggered by the API webhook when a commit lands on the ``projects`` or
``secrets`` config repos. The operation is convergent and single-flight: while a
reconcile runs, concurrent triggers coalesce into one trailing run, so
overlapping ``git pull --rebase`` invocations and docker rollouts can never
interleave. A single uvicorn process serves the API, so an in-process lock is
sufficient (a file lock would only matter under multiple worker processes).
"""

import subprocess
import threading

from instrukt_ai_logging import get_logger

from lib.paths import root
from lib.sync import pull_repos

logger = get_logger(f"itsup.{__name__}")


class ReconcileError(RuntimeError):
    """A reconcile step (pull or apply) failed."""


def _pull_and_apply() -> None:
    """Pull both config repos, then apply the whole stack. Raises on failure."""
    results = pull_repos(root())
    failed = [name for name, ok in results.items() if not ok]
    if failed:
        raise ReconcileError(f"git pull failed for: {', '.join(failed)}")

    # Shell to the CLI so the reconcile reuses apply's validation gate and
    # topological deploy ordering verbatim; there is no single Python entry
    # point that wraps both, and replicating them here would drift from `apply`.
    subprocess.run([str(root() / ".venv" / "bin" / "itsup"), "apply"], check=True)


class _Reconciler:
    """Single-flight, coalescing runner for the full-stack reconcile.

    Only one reconcile runs at a time. A trigger that arrives mid-run sets a
    dirty flag instead of starting a second run; the active run loops once more
    when it sees the flag, so the latest commit is never skipped.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._dirty = False

    def run(self) -> None:
        with self._lock:
            if self._running:
                self._dirty = True
                logger.info("reconcile already in flight; coalescing trigger")
                return
            self._running = True

        try:
            while True:
                with self._lock:
                    self._dirty = False
                logger.info("reconcile: pulling config repos and applying")
                _pull_and_apply()
                logger.debug("reconcile complete")
                with self._lock:
                    if not self._dirty:
                        self._running = False
                        return
                logger.info("config changed during reconcile; running once more")
        except Exception:
            with self._lock:
                self._running = False
                self._dirty = False
            raise


_reconciler = _Reconciler()


def reconcile() -> None:
    """Reconcile the stack from the config repos; single-flight with coalescing."""
    _reconciler.run()
