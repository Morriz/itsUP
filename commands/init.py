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

from commands.common import fail, ok, warn
from lib.paths import (
    display_path,
    project_dir,
    projects_dir,
    root,
    secret_file,
    secrets_dir,
)


def _error(message: str) -> None:
    """Print error message and exit"""
    fail(message)
    sys.exit(1)


def _success(message: str) -> None:
    """Print success message"""
    ok(message)


def _warning(message: str) -> None:
    """Print warning message"""
    warn(message)


def _get_project_root() -> Path:
    """Get the project root directory"""
    return root()


def _validate_project_structure(root: Path) -> None:
    """Validate the resolved root is an itsUP checkout before seeding into it.

    The itsUP-specific ``samples/projects/itsup.yml`` template is the marker: it
    identifies the checkout (no generic project ships it) and init copies from it.
    ``root()`` already anchors identity by the package location; this guards the
    ``ITSUP_ROOT`` override, which resolves to any directory.
    """
    if not (root / "samples" / "projects" / "itsup.yml").is_file():
        _error("Must be run from itsUP project root\n" "  Expected to find samples/projects/itsup.yml")


def _is_git_repo(path: Path) -> bool:
    """Check if a directory is a git repository"""
    return (path / ".git").exists()


def _clone_repo(url: str, path: Path, name: str) -> bool:
    """Clone a git repository to a path

    Returns: True if successful, False if failed
    """
    try:
        subprocess.run(["git", "clone", url, str(path)], check=True, capture_output=True, text=True)

        # Checkout main branch (in case default is different)
        subprocess.run(["git", "checkout", "-B", "main"], cwd=path, check=True, capture_output=True, text=True)

        _success(f"Cloned {name}/ from {url}")
        return True

    except subprocess.CalledProcessError as e:
        _error(f"Failed to clone {name}/: {e.stderr if e.stderr else str(e)}")
        return False


def _setup_sops_diff(repo_path: Path) -> None:
    """Configure sops-diff for git in the secrets repo"""
    try:
        # Create .gitattributes for SOPS diff integration
        gitattributes = repo_path / ".gitattributes"
        gitattributes_content = """# SOPS encrypted files - use sops-diff for meaningful diffs
*.enc.txt diff=sopsdiffer merge=sops
*.enc.json diff=sopsdiffer merge=sops
*.enc.yaml diff=sopsdiffer merge=sops
*.enc.yml diff=sopsdiffer merge=sops
*.enc.env diff=sopsdiffer merge=sops
"""
        if not gitattributes.exists():
            gitattributes.write_text(gitattributes_content)
            _success("Created .gitattributes for sops-diff")

        # Configure git diff command for sops-diff
        subprocess.run(
            ["git", "config", "diff.sopsdiffer.command", "sops-diff --git"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        _success("Configured git diff integration for SOPS files")
    except Exception as e:
        _warning(f"Could not configure sops-diff: {e}")


def _setup_repo(root: Path, name: str) -> None:
    """Setup a git repository (clone if needed, or verify existing)"""
    repo_path = root / name

    # Check if already exists and is a git repo
    if repo_path.exists() and _is_git_repo(repo_path):
        _success(f"{name}/ already exists (git repo)")
        # Still setup sops-diff if this is the secrets repo
        if name == "secrets":
            _setup_sops_diff(repo_path)
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

    # Setup sops-diff if this is the secrets repo
    if name == "secrets":
        _setup_sops_diff(repo_path)


def _copy_if_missing(src: Path, dst: Path) -> None:
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
    _success(f"Copied {display_path(src)} → {display_path(dst)}")

    # Special handling for secrets
    if "secrets" in str(dst):
        _warning("WARNING: Sample secrets copied - MUST be changed before deployment!")


def _copy_dir_if_missing(src: Path, dst: Path) -> None:
    """Copy directory recursively if destination doesn't exist"""
    if dst.exists():
        _success(f"{dst.name}/ already exists (not overwriting)")
        return

    if not src.exists():
        _warning(f"{src.relative_to(src.parent.parent)} not found, skipping")
        return

    # Copy entire directory
    shutil.copytree(src, dst)
    _success(f"Copied {display_path(src)} → {display_path(dst)}")


def _require_source(src: Path) -> None:
    """Fail loudly when a required sample source is absent — a corrupted checkout.

    A missing required template is not a normal skip: seeding on would silently
    produce an incomplete install.
    """
    if not src.exists():
        _error(f"Required sample source is missing: {display_path(src)}\n" "  The itsUP checkout is incomplete.")


def _seed_from(src_dir: Path, dst_dir: Path) -> None:
    """Seed dst_dir with each entry of src_dir, copy-if-missing (never overwriting)."""
    for entry in sorted(src_dir.iterdir()):
        dst = dst_dir / entry.name
        if entry.is_dir():
            _copy_dir_if_missing(entry, dst)
        else:
            _copy_if_missing(entry, dst)


@click.command()
@click.option("--force", is_flag=True, help="Force re-initialization even if already initialized")
def init(force: bool) -> None:
    """🎬 Initialize "projects" and "secrets" repos from samples

    Sets up your itsUP installation by cloning/creating configuration repos
    and copying sample configuration files. Safe to run multiple times.

    \b
    Examples:
        itsup init         # Interactive setup (prompts for git URLs if needed)
        itsup init --force # Force re-initialization
    """
    click.echo("itsUP Initialization")
    click.echo("===================")
    click.echo()

    # Get project root (work from where script is located)
    project_root = _get_project_root()

    # Validate project structure
    _validate_project_structure(project_root)

    # Check if already initialized (exit early unless --force)
    if not force:
        required_files = [
            projects_dir() / "itsup.yml",
            projects_dir() / "traefik.yml",
            secret_file("itsup", encrypted=False),
        ]
        if all(f.exists() for f in required_files):
            _success("Already initialized (use --force to re-run)")
            return

    # Setup git repositories
    click.echo("Setting up configuration repositories...")
    _setup_repo(project_root, "projects")
    _setup_repo(project_root, "secrets")
    click.echo()

    # Initialize configuration files by mirroring the samples/ templates, so the
    # seeded set tracks the samples/ layout with no hardcoded manifest.
    click.echo("Copying configuration files...")
    samples = project_root / "samples"
    _require_source(samples / ".env")
    _require_source(samples / "projects")
    _require_source(samples / "secrets")
    _copy_if_missing(samples / ".env", project_root / ".env")
    _seed_from(samples / "projects", projects_dir())
    _seed_from(samples / "secrets", secrets_dir())
    click.echo()

    # Done
    click.echo("===================")
    _success("Initialization complete!")
    click.echo()
    click.echo("Next steps:")
    click.echo()
    click.echo("1. Edit secrets (CRITICAL - fill in all empty values!):")
    click.echo(f"   vim {display_path(secret_file('itsup', encrypted=False))}   # All secrets (infrastructure + itsUP)")
    click.echo()
    click.echo("2. Edit infrastructure config:")
    click.echo(f"   vim {display_path(projects_dir() / 'itsup.yml')}        # Router IP, versions, backup config")
    click.echo(f"   vim {display_path(projects_dir() / 'traefik.yml')}      # Traefik overrides (log levels, plugins)")
    click.echo(
        f"   vim {display_path(projects_dir() / 'middlewares.yml')}  "
        "# Middleware overrides (rate-limit, auth, crowdsec)"
    )
    click.echo()
    click.echo("3. Add your first project (copy example-project as template):")
    click.echo(f"   cp -r {display_path(project_dir('example-project'))} {display_path(project_dir('my-app'))}")
    click.echo(f"   vim {display_path(project_dir('my-app') / 'docker-compose.yml')}  # Define your service")
    click.echo(f"   vim {display_path(project_dir('my-app') / 'ingress.yml')}         # Configure routing/domain")
    click.echo()
    click.echo("4. Commit to git:")
    click.echo("   itsup status   # Check what changed")
    click.echo("   itsup commit 'Initial configuration'")
    click.echo()
    click.echo("5. Optional - Encrypt secrets:")
    click.echo("   itsup encrypt itsup --delete")
    click.echo()
    click.echo("6. Deploy:")
    click.echo("   itsup apply")
