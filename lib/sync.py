"""Git sync logic for 'itsup pull'."""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _pull_repo(path: Path, name: str) -> bool:
    """Pull a single git repo with rebase.

    Returns True on success, False on failure.
    """
    if not path.exists():
        logger.warning("%s/ directory not found", name)
        return False

    if not (path / ".git").exists():
        logger.warning("%s/ is not a git repository", name)
        return True  # not a failure, just skipped

    try:
        subprocess.run(
            ["git", "pull", "--rebase"],
            cwd=path,
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("%s/ updated", name)
        return True
    except subprocess.CalledProcessError as e:
        # Abort the rebase to leave the repo in a clean state
        subprocess.run(["git", "rebase", "--abort"], cwd=path, check=False, capture_output=True)
        stderr = e.stderr.strip() if e.stderr else str(e)
        logger.error("%s/ pull failed: %s", name, stderr)
        return False


def pull_repos(root: Path | None = None) -> dict[str, bool]:
    """Pull both projects/ and secrets/ repos.

    Args:
        root: Project root directory. Defaults to cwd.

    Returns:
        Dict of {repo_name: success_bool}.
    """
    if root is None:
        root = Path(".")

    return {
        "projects": _pull_repo(root / "projects", "projects"),
        "secrets": _pull_repo(root / "secrets", "secrets"),
    }
