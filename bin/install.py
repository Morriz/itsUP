#!.venv/bin/python

"""
itsUP Installation Script

Validates submodules, copies sample files, creates virtual environment,
and installs Python dependencies.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


class Colors:
    """ANSI color codes for terminal output"""

    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    NC = "\033[0m"  # No Color


def error(message: str) -> None:
    """Print error message and exit"""
    print(f"{Colors.RED}✗ {message}{Colors.NC}", file=sys.stderr)
    sys.exit(1)


def success(message: str) -> None:
    """Print success message"""
    print(f"{Colors.GREEN}✓{Colors.NC} {message}")


def warning(message: str) -> None:
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠{Colors.NC} {message}")


def get_project_root() -> Path:
    """Get the project root directory (where this script lives)"""
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    return project_root


def validate_project_structure(root: Path) -> None:
    """Validate we're in the correct directory"""
    if not (root / "bin" / "install.py").exists() or not (root / "samples").exists():
        error(
            "Must be run from itsUP project root\n"
            "  Expected to find bin/install.py and samples/ directory"
        )


def check_submodule(root: Path, name: str) -> None:
    """Check if a submodule is initialized"""
    submodule_path = root / name
    git_dir = submodule_path / ".git"

    if not git_dir.exists():
        error(
            f"{name}/ submodule not initialized\n"
            "  Run: git submodule update --init --recursive"
        )

    success(f"{name}/ submodule initialized")


def copy_if_missing(src: Path, dst: Path, description: str) -> None:
    """Copy file if destination doesn't exist"""
    if dst.exists():
        success(f"{dst.relative_to(dst.parent.parent)} already exists (not overwriting)")
        return

    if not src.exists():
        warning(f"{src.relative_to(src.parent.parent)} not found, skipping")
        return

    # Ensure parent directory exists
    dst.parent.mkdir(parents=True, exist_ok=True)

    # Copy file
    shutil.copy2(src, dst)
    success(f"Copied {description}")

    # Special handling for secrets
    if "secrets" in str(dst):
        warning("WARNING: Sample secrets copied - MUST be changed before deployment!")


def setup_venv(root: Path) -> None:
    """Create Python virtual environment if needed"""
    venv_path = root / ".venv"

    if venv_path.exists():
        success(".venv already exists")
    else:
        print("Creating Python virtual environment...")
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_path)], check=True, cwd=root
        )
        success("Created .venv")


def install_dependencies(root: Path) -> None:
    """Install Python dependencies"""
    venv_python = root / ".venv" / "bin" / "python"
    venv_pip = root / ".venv" / "bin" / "pip"
    requirements = root / "requirements-prod.txt"

    if not venv_python.exists():
        error(".venv/bin/python not found. Run setup_venv first.")

    print("Installing Python dependencies...")
    subprocess.run(
        [str(venv_pip), "install", "-q", "-r", str(requirements)],
        check=True,
        cwd=root,
    )
    success("Installed Python dependencies")


def main() -> None:
    """Main installation workflow"""
    print("itsUP Installation")
    print("==================")
    print()

    # Get project root (work from where script is located)
    root = get_project_root()
    os.chdir(root)

    # Validate project structure
    validate_project_structure(root)

    # Check submodules
    print("Checking submodules...")
    check_submodule(root, "projects")
    check_submodule(root, "secrets")
    print()

    # Initialize configuration files
    print("Checking configuration files...")
    copy_if_missing(root / "samples" / "env", root / ".env", "samples/env → .env")
    copy_if_missing(
        root / "samples" / "traefik.yml",
        root / "projects" / "traefik.yml",
        "samples/traefik.yml → projects/traefik.yml",
    )
    copy_if_missing(
        root / "samples" / "secrets" / "global.txt",
        root / "secrets" / "global.txt",
        "samples/secrets/global.txt → secrets/global.txt",
    )
    print()

    # Create Python virtual environment
    print("Setting up Python environment...")
    setup_venv(root)
    install_dependencies(root)
    print()

    # Done
    print("==================")
    success("Installation complete!")
    print()
    print("Next steps:")
    print("1. Edit .env (configure environment variables)")
    print("2. Edit projects/traefik.yml (change domain_suffix to your domain)")
    print("3. Edit secrets/global.txt (fill in all required secrets - CRITICAL!)")
    print("4. Encrypt secrets: cd secrets && sops -e global.txt > global.enc.txt")
    print("5. Commit configs to git (in projects/ and secrets/ submodules)")
    print("6. Deploy: bin/apply.py")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        error(f"Command failed: {e}")
    except KeyboardInterrupt:
        print()
        error("Installation interrupted")
    except Exception as e:
        error(f"Unexpected error: {e}")
