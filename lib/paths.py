"""Path resolution and display for the itsUP CLI.

Single source of truth for every location itsUP reads, writes, or reports: the
install root (``ITSUP_ROOT`` when set, otherwise the repo root derived from this
package's location), the data trees rooted in it, and the rendering of a
location for a terminal caller. Callers compose locations from the helpers here
rather than from their own ``root() / "..."`` expressions or literal strings, so
a location is resolved one way and rendered one way. Stdlib-only (``os`` /
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


def secrets_dir() -> Path:
    """Resolve the secrets tree."""
    return root() / "secrets"


def secret_file(name: str, *, encrypted: bool) -> Path:
    """Resolve a named secret file — encrypted ``<name>.enc.txt`` or plaintext ``<name>.txt``."""
    return secrets_dir() / f"{name}{'.enc.txt' if encrypted else '.txt'}"


def sops_config_file() -> Path:
    """Resolve the SOPS creation-rules config."""
    return secrets_dir() / ".sops.yaml"


def projects_dir() -> Path:
    """Resolve the projects tree."""
    return root() / "projects"


def project_dir(name: str) -> Path:
    """Resolve one project's config directory."""
    return projects_dir() / name


def display_path(path: Path) -> str:
    """Format a file location so it is usable from the caller's actual cwd.

    Returns the path relative to the install root when the caller is standing in
    the install root, absolute otherwise — so a caller invoking itsup from
    anywhere gets a location it can act on without knowing where the install root
    lives. Every location itsUP prints goes through here; a literal path string
    in output is a defect, because it is only correct from one cwd.

    Resolves both sides before comparing: ``cwd()`` returns the OS-resolved path
    (e.g. macOS ``/var`` -> ``/private/var``), which a literal ``ITSUP_ROOT``
    would otherwise never match.
    """
    resolved_root = root().resolve()
    resolved_path = path.resolve()
    if Path.cwd().resolve() == resolved_root:
        return str(resolved_path.relative_to(resolved_root))
    return str(resolved_path)
