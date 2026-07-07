#!/usr/bin/env python3

"""
itsup commit command

Commit changes to "projects" and "secrets" repos.
"""

import subprocess
import sys
from pathlib import Path

import click

from commands.common import fail, ok, warn
from lib.paths import root as install_root


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


def _commit_and_push(path: Path, name: str, message: str, force: bool = False) -> bool:
    """Commit and push changes in a repo

    Args:
        path: Path to the git repo
        name: Display name of the repo
        message: Commit message to use
        force: If True, skip rebase and force push

    Returns: True if successful, False if failed
    """
    try:
        subprocess.run(["git", "add", "-A"], cwd=path, check=True)
        subprocess.run(["git", "commit", "-m", message], cwd=path, check=True)

        ok(f"{name}/ committed: {message}")

        # Pull with rebase to handle diverged branches (unless force)
        if not force:
            try:
                subprocess.run(["git", "pull", "--rebase"], cwd=path, check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                # Rebase conflict - abort and warn user
                subprocess.run(["git", "rebase", "--abort"], cwd=path, check=False)
                fail(f"{name}/ pull --rebase failed (conflicts)")
                click.echo(f"  Run manually: cd {name} && git pull --rebase", err=True)
                click.echo(f"  Or use --force to override remote", err=True)
                return False

        # Push (force if requested)
        push_cmd = ["git", "push", "--force-with-lease"] if force else ["git", "push"]
        subprocess.run(push_cmd, cwd=path, check=True)

        push_msg = "force pushed" if force else "pushed"
        ok(f"{name}/ {push_msg} to origin")
        return True

    except subprocess.CalledProcessError as e:
        fail(f"{name}/ failed: {e}")
        return False


@click.command()
@click.option("--force", "-f", is_flag=True, help="Skip encryption prompts and commit as-is")
def commit(force: bool) -> None:
    """💾 Commit and push changes to "projects" and "secrets" repos

    Commits changes to both configuration repos and pushes to origin.
    Commit message is always auto-generated. Detects key rotation.
    Auto-encrypts plaintext secrets before committing for security.

    \b
    Examples:
        itsup commit          # Auto-generated message
        itsup commit -f       # Force commit, skip encryption prompts
    """
    # Get project root
    repo_root = install_root()

    projects_path = repo_root / "projects"
    secrets_path = repo_root / "secrets"

    # Check for changes
    projects_dirty = _has_changes(projects_path)
    secrets_dirty = _has_changes(secrets_path)

    if not projects_dirty and not secrets_dirty:
        ok("No changes to commit")
        return

    # Show what will be committed
    click.echo("Changes detected in:")
    if projects_dirty:
        click.echo(f"  - {click.style('projects/', fg='yellow')}")
    if secrets_dirty:
        click.echo(f"  - {click.style('secrets/', fg='yellow')}")
    click.echo()

    # Security check: Warn about plaintext secrets in secrets/
    if secrets_dirty:
        plaintext_secrets = [f for f in secrets_path.glob("*.txt") if not f.name.endswith(".enc.txt")]
        if plaintext_secrets:
            warn("Warning: Plaintext secrets detected in secrets/")
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
                    warn("Proceeding without encryption")
                    click.echo(f"  Note: Plaintext .txt files are in .gitignore and won't be committed")
                    click.echo()
                else:
                    click.echo()
                    click.echo("Encrypting secrets...")
                    # Run itsup encrypt --delete
                    try:
                        subprocess.run([str(repo_root / "bin" / "itsup"), "encrypt", "--delete"], check=True)
                        ok("Secrets encrypted and plaintext removed")
                        click.echo()
                    except subprocess.CalledProcessError as e:
                        fail(f"Failed to encrypt secrets: {e}")
                        sys.exit(1)
            else:
                warn("SOPS not installed - cannot encrypt")
                click.echo("  Install with: brew install sops")
                click.echo(f"  Note: Plaintext .txt files are in .gitignore and won't be committed")
                click.echo()

    # Detect key rotation for secrets repo
    key_rotation = False
    if secrets_dirty:
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
        projects_msg = "Update configuration"
        click.echo(f"projects/ message: {click.style(projects_msg, fg='yellow')}")
        if not _commit_and_push(projects_path, "projects", projects_msg, force=force):
            success = False

    if secrets_dirty:
        secrets_msg = "Rotate SOPS encryption key" if key_rotation else "Update secrets"
        click.echo(f"secrets/ message: {click.style(secrets_msg, fg='yellow')}")
        if not _commit_and_push(secrets_path, "secrets", secrets_msg, force=force):
            success = False

    click.echo()

    if success:
        ok("All repos committed and pushed")
    else:
        fail("Some commits failed")
        sys.exit(1)
