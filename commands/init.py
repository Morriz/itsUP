#!.venv/bin/python

"""
itsup init command

Initializes new itsUP installation by validating prerequisites and copying sample files.
"""

import shutil
import sys
from pathlib import Path

import click


class Colors:
    """ANSI color codes for terminal output"""

    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    NC = "\033[0m"  # No Color


def _error(message: str) -> None:
    """Print error message and exit"""
    click.echo(f"{Colors.RED}✗ {message}{Colors.NC}", err=True)
    sys.exit(1)


def _success(message: str) -> None:
    """Print success message"""
    click.echo(f"{Colors.GREEN}✓{Colors.NC} {message}")


def _warning(message: str) -> None:
    """Print warning message"""
    click.echo(f"{Colors.YELLOW}⚠{Colors.NC} {message}")


def _get_project_root() -> Path:
    """Get the project root directory"""
    # itsup script is in project root, commands/ is also in project root
    # So we go up from commands/ directory
    commands_dir = Path(__file__).resolve().parent
    project_root = commands_dir.parent
    return project_root


def _validate_project_structure(root: Path) -> None:
    """Validate we're in the correct directory"""
    if not (root / "itsup").exists() or not (root / "samples").exists():
        _error(
            "Must be run from itsUP project root\n"
            "  Expected to find itsup and samples/ directory"
        )


def _check_submodule(root: Path, name: str) -> None:
    """Check if a submodule is initialized"""
    submodule_path = root / name
    git_dir = submodule_path / ".git"

    if not git_dir.exists():
        _error(
            f"{name}/ submodule not initialized\n"
            "  Run: git submodule update --init --recursive"
        )

    _success(f"{name}/ submodule initialized")


def _copy_if_missing(src: Path, dst: Path, description: str) -> None:
    """Copy file if destination doesn't exist"""
    if dst.exists():
        _success(f"{dst.name} already exists (not overwriting)")
        return

    if not src.exists():
        _warning(f"{src.relative_to(src.parent.parent)} not found, skipping")
        return

    # Ensure parent directory exists
    dst.parent.mkdir(parents=True, exist_ok=True)

    # Copy file
    shutil.copy2(src, dst)
    _success(f"Copied {description}")

    # Special handling for secrets
    if "secrets" in str(dst):
        _warning("WARNING: Sample secrets copied - MUST be changed before deployment!")


@click.command()
def init():
    """Initialize new installation from samples"""
    click.echo("itsUP Initialization")
    click.echo("===================")
    click.echo()

    # Get project root (work from where script is located)
    root = _get_project_root()

    # Validate project structure
    _validate_project_structure(root)

    # Check if already initialized
    if (root / "projects" / "traefik.yml").exists():
        _error("Already initialized: projects/traefik.yml exists")

    # Check submodules
    click.echo("Checking submodules...")
    _check_submodule(root, "projects")
    _check_submodule(root, "secrets")
    click.echo()

    # Initialize configuration files
    click.echo("Copying configuration files...")
    _copy_if_missing(root / "samples" / "env", root / ".env", "samples/env → .env")
    _copy_if_missing(
        root / "samples" / "traefik.yml",
        root / "projects" / "traefik.yml",
        "samples/traefik.yml → projects/traefik.yml",
    )
    _copy_if_missing(
        root / "samples" / "secrets" / "global.txt",
        root / "secrets" / "global.txt",
        "samples/secrets/global.txt → secrets/global.txt",
    )
    click.echo()

    # Done
    click.echo("===================")
    _success("Initialization complete!")
    click.echo()
    click.echo("Next steps:")
    click.echo("1. Run: make install (or bin/install.sh) to setup Python environment")
    click.echo("2. Edit .env (configure environment variables)")
    click.echo("3. Edit projects/traefik.yml (change domain_suffix to your domain)")
    click.echo("4. Edit secrets/global.txt (fill in all required secrets - CRITICAL!)")
    click.echo("5. Encrypt secrets: cd secrets && sops -e global.txt > global.enc.txt")
    click.echo("6. Commit configs to git (in projects/ and secrets/ submodules)")
    click.echo("7. Deploy: bin/apply.py")
