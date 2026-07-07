#!/usr/bin/env python3

"""
itsup diff-secrets command

Compare encrypted SOPS files to show meaningful diffs of secret changes.
"""

import subprocess
import sys

import click

from commands.common import fail, warn
from lib.paths import root as install_root


def _check_sops_diff() -> bool:
    """Check if sops-diff is installed."""
    try:
        subprocess.run(["sops-diff", "--version"], capture_output=True, check=True, timeout=5)
        return True
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return False


@click.command()
@click.argument("file1", required=False)
@click.argument("file2", required=False)
@click.option("--summary", is_flag=True, help="Show summary instead of full diff")
@click.option("--git", is_flag=True, help="Use git refs (e.g., HEAD:secrets/itsup.enc.txt)")
def diff_secrets(file1: str, file2: str, summary: bool, git: bool) -> None:
    """🔍 Show meaningful diffs of encrypted secrets

    Compare SOPS-encrypted files to see actual content changes.

    Without arguments: Shows git diff for all *.enc.txt files in secrets/

    \b
    Examples:
        # Diff all encrypted secrets vs git HEAD
        itsup diff-secrets

        # Compare two encrypted files
        itsup diff-secrets secrets/itsup.enc.txt secrets/itsup-old.enc.txt

        # Compare current file with git revision
        itsup diff-secrets --git HEAD:secrets/itsup.enc.txt secrets/itsup.enc.txt

        # Show summary only
        itsup diff-secrets --summary secrets/itsup.enc.txt secrets/itsup-old.enc.txt

    Note: When using --git, FILE1 can be a git ref like:
        HEAD:path/to/file.enc.txt
        main:path/to/file.enc.txt
        feature-branch:path/to/file.enc.txt
    """
    if not _check_sops_diff():
        fail("sops-diff is not installed")
        click.echo()
        click.echo("Install sops-diff:")
        click.echo("  Run: bin/install.sh")
        click.echo("  Or manually from: https://github.com/saltydogtechnology/sops-diff")
        click.echo()
        sys.exit(1)

    # No arguments: iterate over all encrypted files in secrets/
    if not file1:
        repo_root = install_root()
        secrets_dir = repo_root / "secrets"

        if not secrets_dir.exists():
            fail("secrets/ directory not found")
            sys.exit(1)

        encrypted_files = sorted(secrets_dir.glob("*.enc.txt"))

        if not encrypted_files:
            warn("No encrypted files found in secrets/")
            sys.exit(0)

        has_changes = False
        for enc_file in encrypted_files:
            # Show diff vs git HEAD
            rel_path = enc_file.relative_to(repo_root)

            # Check if file exists in git HEAD of secrets repo
            check_in_git = subprocess.run(
                ["git", "cat-file", "-e", f"HEAD:{enc_file.name}"], cwd=secrets_dir, capture_output=True, check=False
            )

            if check_in_git.returncode != 0:
                # File not in git yet - show decrypted content
                click.echo(click.style(f"=== {rel_path} ===", fg="blue"))
                click.echo(click.style("+ New file (not yet in git)", fg="green"))
                click.echo()

                # Decrypt and show content
                try:
                    result = subprocess.run(["sops", "-d", str(enc_file)], capture_output=True, check=True, text=True)
                    for line in result.stdout.splitlines():
                        click.echo(click.style(f"+ {line}", fg="green"))
                except subprocess.CalledProcessError:
                    fail("Failed to decrypt")

                click.echo()
                has_changes = True
                continue

            cmd = ["sops-diff", "--git", f"HEAD:{enc_file.name}", str(enc_file)]

            if summary:
                cmd.insert(1, "--summary")

            click.echo(click.style(f"=== {rel_path} ===", fg="blue"))
            result = subprocess.run(cmd, cwd=secrets_dir, check=False, text=True)

            if result.returncode != 0:
                has_changes = True

            click.echo()

        sys.exit(1 if has_changes else 0)

    # Build command for specific files
    cmd = ["sops-diff"]

    if summary:
        cmd.append("--summary")

    if git:
        cmd.append("--git")
        # For git mode, file1 should contain the ref, file2 is optional
        cmd.append(file1)
        if file2:
            cmd.append(file2)
    else:
        # Regular file comparison requires both files
        if not file2:
            fail("FILE2 required (or use --git flag)")
            sys.exit(1)

        # Validate files exist
        repo_root = install_root()
        f1 = repo_root / file1
        f2 = repo_root / file2

        if not f1.exists():
            fail(f"File not found: {file1}")
            sys.exit(1)

        if not f2.exists():
            fail(f"File not found: {file2}")
            sys.exit(1)

        cmd.extend([str(f1), str(f2)])

    # Run sops-diff
    try:
        result = subprocess.run(cmd, check=False, text=True)
        sys.exit(result.returncode)
    except Exception as e:
        fail(f"Failed to run sops-diff: {e}")
        sys.exit(1)
