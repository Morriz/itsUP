"""Install-root resolution for the itsUP CLI.

Single source of truth for the install root: ``ITSUP_ROOT`` when set, otherwise
the repo root derived from this package's location. Stdlib-only (``os`` /
``pathlib``) to avoid import cycles — every data module imports it.
"""

import os
from pathlib import Path


def root() -> Path:
    """Resolve the itsUP install root.

    Returns ``Path(ITSUP_ROOT)`` when the env var is set and non-empty;
    otherwise derives the repo root from this file's location (``lib/`` lives
    directly under the repo root, the anchor ``commands/*`` already use).

    Fails closed: when ``ITSUP_ROOT`` points at a missing directory, or when the
    package is installed outside the repo tree (a non-editable / site-packages
    install) so the derived path is not the itsUP root, a clear configuration
    error naming ``ITSUP_ROOT`` is raised rather than silently reading the wrong
    tree.
    """
    env_root = os.environ.get("ITSUP_ROOT")
    if env_root:
        path = Path(env_root)
        if not path.is_dir():
            raise RuntimeError(f"ITSUP_ROOT is set to {env_root!r} but that directory does not exist")
        return path

    derived = Path(__file__).resolve().parent.parent
    # pyproject.toml marks the repo root; its absence means we resolved a
    # non-editable install location, where the data tree cannot be derived.
    if not (derived / "pyproject.toml").is_file():
        raise RuntimeError(
            "Cannot derive the itsUP install root from the package location; " "set ITSUP_ROOT to the repository path"
        )
    return derived
