#!/usr/bin/env python3

"""
itsup commit command

Commit changes to "projects" and "secrets" repos.
"""

import subprocess
import sys
from pathlib import Path

import click

from commands.common import fail, ok
from lib.paths import display_path, projects_dir, secrets_dir
from lib.sops import encrypt_plaintext_secrets, is_sops_available


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
@click.option("--force", "-f", is_flag=True, help="Skip rebase and force-push")
def commit(force: bool) -> None:
    """💾 Commit and push changes to "projects" and "secrets" repos

    Commits changes to both configuration repos and pushes to origin.
    Commit message is always auto-generated. Detects key rotation.
    Auto-encrypts plaintext secrets before committing; fails closed (no
    commit) rather than silently dropping an un-encrypted edit when SOPS
    is unavailable.

    \b
    Examples:
        itsup commit          # Auto-generated message
        itsup commit -f       # Skip rebase, force-push
    """
    projects_path = projects_dir()
    secrets_path = secrets_dir()

    # Preflight: encrypt any plaintext secrets before deciding what's dirty.
    # secrets/*.txt is gitignored, so a plaintext-only edit leaves git clean
    # and would otherwise be silently dropped by the dirty check below.
    if secrets_path.exists():
        plaintext_secrets = [f for f in secrets_path.glob("*.txt") if not f.name.endswith(".enc.txt")]
        if plaintext_secrets:
            if not is_sops_available():
                fail("Plaintext secrets present but SOPS is not installed")
                for secret_file in plaintext_secrets:
                    click.echo(f"  - {secret_file.name}")
                click.echo("  Install SOPS (brew install sops) or encrypt manually before committing")
                sys.exit(1)

            click.echo("Encrypting secrets...")
            result = encrypt_plaintext_secrets(secrets_path, delete=True)
            if result.failed:
                fail(f"Failed to encrypt: {', '.join(p.name for p in result.failed)}")
                sys.exit(1)
            if result.encrypted:
                ok(f"Encrypted {len(result.encrypted)} file(s)")
            click.echo()

    # Check for changes
    projects_dirty = _has_changes(projects_path)
    secrets_dirty = _has_changes(secrets_path)

    if not projects_dirty and not secrets_dirty:
        ok("No changes to commit")
        return

    # Show what will be committed
    click.echo("Changes detected in:")
    if projects_dirty:
        click.echo(f"  - {click.style(display_path(projects_path), fg='yellow')}")
    if secrets_dirty:
        click.echo(f"  - {click.style(display_path(secrets_path), fg='yellow')}")
    click.echo()

    # Detect key rotation for secrets repo
    key_rotation = False
    if secrets_dirty:
        sops_yaml_changed = False
        try:
            diff_result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=secrets_path,
                capture_output=True,
                text=True,
                check=True,
            )
            if ".sops.yaml" in diff_result.stdout:
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
        click.echo(f"{display_path(projects_path)} message: {click.style(projects_msg, fg='yellow')}")
        if not _commit_and_push(projects_path, "projects", projects_msg, force=force):
            success = False

    if secrets_dirty:
        secrets_msg = "Rotate SOPS encryption key" if key_rotation else "Update secrets"
        click.echo(f"{display_path(secrets_path)} message: {click.style(secrets_msg, fg='yellow')}")
        if not _commit_and_push(secrets_path, "secrets", secrets_msg, force=force):
            success = False

    click.echo()

    if success:
        ok("All repos committed and pushed")
    else:
        fail("Some commits failed")
        sys.exit(1)
