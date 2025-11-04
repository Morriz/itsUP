#!/usr/bin/env python3

"""
itsup commit command

Commit changes to "projects" and "secrets" repos.
"""

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


def _has_changes(path: Path) -> bool:
    """Check if a git repo has uncommitted changes"""
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        return bool(result.stdout.strip())
    except subprocess.CalledProcessError:
        return False


def _commit_and_push(path: Path, name: str, message: str, custom_message: str = None, force: bool = False) -> bool:
    """Commit and push changes in a repo

    Args:
        path: Path to the git repo
        name: Display name of the repo
        message: Commit message to use (only if custom_message not provided)
        custom_message: Optional custom message (overrides message)
        force: If True, skip rebase and force push

    Returns: True if successful, False if failed
    """
    try:
        # Add all changes
        subprocess.run(["git", "add", "-A"], cwd=path, check=True)

        # Use custom message if provided, otherwise use generated message
        commit_msg = custom_message if custom_message else message

        # Commit
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=path, check=True)

        click.echo(f"{Colors.GREEN}✓{Colors.NC} {name}/ committed: {commit_msg}")

        # Pull with rebase to handle diverged branches (unless force)
        if not force:
            try:
                subprocess.run(["git", "pull", "--rebase"], cwd=path, check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                # Rebase conflict - abort and warn user
                subprocess.run(["git", "rebase", "--abort"], cwd=path, check=False)
                click.echo(f"{Colors.RED}✗{Colors.NC} {name}/ pull --rebase failed (conflicts)", err=True)
                click.echo(f"  Run manually: cd {name} && git pull --rebase", err=True)
                click.echo(f"  Or use --force to override remote", err=True)
                return False

        # Push (force if requested)
        push_cmd = ["git", "push", "--force-with-lease"] if force else ["git", "push"]
        subprocess.run(push_cmd, cwd=path, check=True)

        push_msg = "force pushed" if force else "pushed"
        click.echo(f"{Colors.GREEN}✓{Colors.NC} {name}/ {push_msg} to origin")
        return True

    except subprocess.CalledProcessError as e:
        click.echo(f"{Colors.RED}✗{Colors.NC} {name}/ failed: {e}", err=True)
        return False


@click.command()
@click.argument("message", required=False)
@click.option("--force", "-f", is_flag=True, help="Skip encryption prompts and commit as-is")
def commit(message, force):
    """💾 Commit and push changes to "projects" and "secrets" repos [MESSAGE]

    Commits changes to both configuration repos and pushes to origin.
    Auto-generates commit message if not provided. Detects key rotation.
    Auto-encrypts plaintext secrets before committing for security.

    \b
    Examples:
        itsup commit                          # Auto-generated message
        itsup commit "feat: add new service"  # Custom message
        itsup commit -f                       # Force commit, skip encryption prompts
    """
    # Get project root
    root = Path(__file__).resolve().parent.parent

    projects_path = root / "projects"
    secrets_path = root / "secrets"

    # Check for changes
    projects_dirty = _has_changes(projects_path)
    secrets_dirty = _has_changes(secrets_path)

    if not projects_dirty and not secrets_dirty:
        click.echo(f"{Colors.GREEN}✓{Colors.NC} No changes to commit")
        return

    # Show what will be committed
    click.echo("Changes detected in:")
    if projects_dirty:
        click.echo(f"  - {Colors.YELLOW}projects/{Colors.NC}")
    if secrets_dirty:
        click.echo(f"  - {Colors.YELLOW}secrets/{Colors.NC}")
    click.echo()

    # Security check: Warn about plaintext secrets in secrets/
    if secrets_dirty:
        plaintext_secrets = [f for f in secrets_path.glob("*.txt") if not f.name.endswith(".enc.txt")]
        if plaintext_secrets:
            click.echo(f"{Colors.YELLOW}⚠ Warning: Plaintext secrets detected in secrets/{Colors.NC}")
            for secret_file in plaintext_secrets:
                click.echo(f"  - {secret_file.name}")
            click.echo()

            # Check if SOPS is available
            try:
                subprocess.run(["sops", "--version"], capture_output=True, check=True, timeout=5)
                sops_available = True
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                sops_available = False

            if sops_available:
                if force or not click.confirm("Encrypt secrets before committing?", default=True):
                    click.echo()
                    click.echo(f"{Colors.YELLOW}⚠{Colors.NC} Proceeding without encryption")
                    click.echo(f"  Note: Plaintext .txt files are in .gitignore and won't be committed")
                    click.echo()
                else:
                    click.echo()
                    click.echo("Encrypting secrets...")
                    # Run itsup encrypt --delete
                    try:
                        subprocess.run(["bin/itsup", "encrypt", "--delete"], check=True)
                        click.echo(f"{Colors.GREEN}✓{Colors.NC} Secrets encrypted and plaintext removed")
                        click.echo()
                    except subprocess.CalledProcessError as e:
                        click.echo(f"{Colors.RED}✗{Colors.NC} Failed to encrypt secrets: {e}", err=True)
                        sys.exit(1)
            else:
                click.echo(f"{Colors.YELLOW}⚠{Colors.NC} SOPS not installed - cannot encrypt")
                click.echo("  Install with: brew install sops")
                click.echo(f"  Note: Plaintext .txt files are in .gitignore and won't be committed")
                click.echo()

    # Detect key rotation for secrets repo
    key_rotation = False
    if secrets_dirty and not message:
        sops_yaml_changed = False
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=secrets_path,
                capture_output=True,
                text=True,
                check=True,
            )
            if ".sops.yaml" in result.stdout:
                sops_yaml_changed = True
        except subprocess.CalledProcessError:
            pass

        # Check for backup keys (indicator of rotation)
        keys_dir = Path.home() / ".config" / "sops" / "age"
        backup_keys = list(keys_dir.glob("keys.txt.backup.*")) if keys_dir.exists() else []

        if sops_yaml_changed and backup_keys:
            key_rotation = True

    # Commit each dirty repo with appropriate message
    success = True

    if projects_dirty:
        projects_msg = message if message else "Update configuration"
        click.echo(f"projects/ message: {Colors.YELLOW}{projects_msg}{Colors.NC}")
        if not _commit_and_push(projects_path, "projects", projects_msg, force=force):
            success = False

    if secrets_dirty:
        if message:
            secrets_msg = message
        elif key_rotation:
            secrets_msg = "Rotate SOPS encryption key"
        else:
            secrets_msg = "Update secrets"

        click.echo(f"secrets/ message: {Colors.YELLOW}{secrets_msg}{Colors.NC}")
        if not _commit_and_push(secrets_path, "secrets", secrets_msg, force=force):
            success = False

    click.echo()

    if success:
        click.echo(f"{Colors.GREEN}✓{Colors.NC} All repos committed and pushed")
    else:
        click.echo(f"{Colors.RED}✗{Colors.NC} Some commits failed", err=True)
        sys.exit(1)
