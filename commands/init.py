#!.venv/bin/python

"""
itsup init command

Initializes new itsUP installation by validating prerequisites and copying sample files.
"""

import shutil
import subprocess
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
        _error("Must be run from itsUP project root\n" "  Expected to find itsup and samples/ directory")


def _is_git_repo(path: Path) -> bool:
    """Check if a directory is a git repository"""
    return (path / ".git").exists()


def _clone_repo(url: str, path: Path, name: str) -> bool:
    """Clone a git repository to a path

    Returns: True if successful, False if failed
    """
    try:
        subprocess.run(
            ["git", "clone", url, str(path)],
            check=True,
            capture_output=True,
            text=True
        )

        # Checkout main branch (in case default is different)
        subprocess.run(
            ["git", "checkout", "-B", "main"],
            cwd=path,
            check=True,
            capture_output=True,
            text=True
        )

        _success(f"Cloned {name}/ from {url}")
        return True

    except subprocess.CalledProcessError as e:
        _error(f"Failed to clone {name}/: {e.stderr if e.stderr else str(e)}")
        return False


def _setup_repo(root: Path, name: str) -> None:
    """Setup a git repository (clone if needed, or verify existing)"""
    repo_path = root / name

    # Check if already exists and is a git repo
    if repo_path.exists() and _is_git_repo(repo_path):
        _success(f"{name}/ already exists (git repo)")
        return

    # Need to clone - prompt for URL
    click.echo()
    click.echo(f"Setting up {name}/ repository...")
    click.echo(f"You need a private git repository for {name}/")
    click.echo()

    if name == "projects":
        click.echo("This will contain:")
        click.echo("  - Service configurations (docker-compose.yml)")
        click.echo("  - Routing config (ingress.yml)")
        click.echo("  - Traefik overrides (traefik.yml)")
    else:  # secrets
        click.echo("This will contain:")
        click.echo("  - All secrets (encrypted with sops)")
        click.echo("  - Infrastructure + project secrets")

    click.echo()

    # Prompt for URL
    url = click.prompt(f"Git URL for {name}/ repo", type=str)

    if not url.strip():
        _error("Repository URL cannot be empty")

    # Clone the repo
    _clone_repo(url, repo_path, name)


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


def _copy_dir_if_missing(src: Path, dst: Path, description: str) -> None:
    """Copy directory recursively if destination doesn't exist"""
    if dst.exists():
        _success(f"{dst.name}/ already exists (not overwriting)")
        return

    if not src.exists():
        _warning(f"{src.relative_to(src.parent.parent)} not found, skipping")
        return

    # Copy entire directory
    shutil.copytree(src, dst)
    _success(f"Copied {description}")


@click.command()
@click.option("--force", is_flag=True, help="Force re-initialization even if already initialized")
def init(force: bool):
    """🎬 Initialize "projects" and "secrets" repos from samples

    Sets up your itsUP installation by cloning/creating configuration repos
    and copying sample configuration files. Safe to run multiple times.

    Examples:
        itsup init         # Interactive setup (prompts for git URLs if needed)
        itsup init --force # Force re-initialization
    """
    click.echo("itsUP Initialization")
    click.echo("===================")
    click.echo()

    # Get project root (work from where script is located)
    root = _get_project_root()

    # Validate project structure
    _validate_project_structure(root)

    # Check if already initialized (exit early unless --force)
    if not force:
        required_files = [
            root / "projects" / "itsup.yml",
            root / "projects" / "traefik.yml",
            root / "secrets" / "itsup.txt",
        ]
        if all(f.exists() for f in required_files):
            _success("Already initialized (use --force to re-run)")
            return

    # Setup git repositories
    click.echo("Setting up configuration repositories...")
    _setup_repo(root, "projects")
    _setup_repo(root, "secrets")
    click.echo()

    # Initialize configuration files
    click.echo("Copying configuration files...")
    _copy_if_missing(root / "samples" / "env", root / ".env", "samples/env → .env")
    _copy_if_missing(
        root / "samples" / "itsup.yml",
        root / "projects" / "itsup.yml",
        "samples/itsup.yml → projects/itsup.yml",
    )
    _copy_if_missing(
        root / "samples" / "traefik.yml",
        root / "projects" / "traefik.yml",
        "samples/traefik.yml → projects/traefik.yml",
    )
    _copy_dir_if_missing(
        root / "samples" / "example-project",
        root / "projects" / "example-project",
        "samples/example-project/ → projects/example-project/",
    )
    _copy_if_missing(
        root / "samples" / "secrets" / "itsup.txt",
        root / "secrets" / "itsup.txt",
        "samples/secrets/itsup.txt → secrets/itsup.txt",
    )
    click.echo()

    # Done
    click.echo("===================")
    _success("Initialization complete!")
    click.echo()
    click.echo("Next steps:")
    click.echo()
    click.echo("1. Edit secrets (CRITICAL - fill in all empty values!):")
    click.echo("   vim secrets/itsup.txt   # All secrets (infrastructure + itsUP)")
    click.echo()
    click.echo("2. Edit infrastructure config:")
    click.echo("   vim projects/itsup.yml   # Router IP, versions, backup config")
    click.echo("   vim projects/traefik.yml # Traefik overrides (domains, log levels, plugins)")
    click.echo()
    click.echo("3. Add your first project (copy example-project as template):")
    click.echo("   cp -r projects/example-project projects/my-app")
    click.echo("   vim projects/my-app/docker-compose.yml  # Define your service")
    click.echo("   vim projects/my-app/ingress.yml         # Configure routing/domain")
    click.echo()
    click.echo("4. Commit to git:")
    click.echo("   itsup status   # Check what changed")
    click.echo("   itsup commit 'Initial configuration'")
    click.echo()
    click.echo("5. Optional - Encrypt secrets:")
    click.echo("   cd secrets && sops -e itsup.txt > itsup.enc.txt")
    click.echo()
    click.echo("6. Deploy:")
    click.echo("   itsup apply")
