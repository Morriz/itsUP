#!/usr/bin/env python3

"""
itsup diff-secrets command

Compare encrypted SOPS files to show meaningful diffs of secret changes.
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
    BLUE = "\033[0;34m"
    NC = "\033[0m"  # No Color


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
def diff_secrets(file1: str, file2: str, summary: bool, git: bool):
    """🔍 Show meaningful diffs of encrypted secrets

    Compare SOPS-encrypted files to see actual content changes.

    Without arguments: Shows git diff for all *.enc.txt files in secrets/

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
        click.echo(f"{Colors.RED}✗{Colors.NC} sops-diff is not installed", err=True)
        click.echo()
        click.echo("Install sops-diff:")
        click.echo("  Run: bin/install.sh")
        click.echo("  Or manually from: https://github.com/saltydogtechnology/sops-diff")
        click.echo()
        sys.exit(1)

    # No arguments: iterate over all encrypted files in secrets/
    if not file1:
        root = Path(__file__).resolve().parent.parent
        secrets_dir = root / "secrets"

        if not secrets_dir.exists():
            click.echo(f"{Colors.RED}✗{Colors.NC} secrets/ directory not found", err=True)
            sys.exit(1)

        encrypted_files = sorted(secrets_dir.glob("*.enc.txt"))

        if not encrypted_files:
            click.echo(f"{Colors.YELLOW}⚠{Colors.NC} No encrypted files found in secrets/")
            sys.exit(0)

        has_changes = False
        for enc_file in encrypted_files:
            # Show diff vs git HEAD
            rel_path = enc_file.relative_to(root)

            # Check if file exists in git HEAD of secrets repo
            check_in_git = subprocess.run(
                ["git", "cat-file", "-e", f"HEAD:{enc_file.name}"],
                cwd=secrets_dir,
                capture_output=True,
                check=False
            )

            if check_in_git.returncode != 0:
                # File not in git yet - show decrypted content
                click.echo(f"{Colors.BLUE}=== {rel_path} ==={Colors.NC}")
                click.echo(f"{Colors.GREEN}+ New file (not yet in git){Colors.NC}")
                click.echo()

                # Decrypt and show content
                try:
                    result = subprocess.run(
                        ["sops", "-d", str(enc_file)],
                        capture_output=True,
                        check=True,
                        text=True
                    )
                    for line in result.stdout.splitlines():
                        click.echo(f"{Colors.GREEN}+ {line}{Colors.NC}")
                except subprocess.CalledProcessError:
                    click.echo(f"{Colors.RED}✗ Failed to decrypt{Colors.NC}")

                click.echo()
                has_changes = True
                continue

            cmd = ["sops-diff", "--git", f"HEAD:{enc_file.name}", str(enc_file)]

            if summary:
                cmd.insert(1, "--summary")

            click.echo(f"{Colors.BLUE}=== {rel_path} ==={Colors.NC}")
            result = subprocess.run(cmd, cwd=secrets_dir, check=False)

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
            click.echo(
                f"{Colors.RED}✗{Colors.NC} FILE2 required (or use --git flag)",
                err=True,
            )
            sys.exit(1)

        # Validate files exist
        root = Path(__file__).resolve().parent.parent
        f1 = root / file1
        f2 = root / file2

        if not f1.exists():
            click.echo(f"{Colors.RED}✗{Colors.NC} File not found: {file1}", err=True)
            sys.exit(1)

        if not f2.exists():
            click.echo(f"{Colors.RED}✗{Colors.NC} File not found: {file2}", err=True)
            sys.exit(1)

        cmd.extend([str(f1), str(f2)])

    # Run sops-diff
    try:
        result = subprocess.run(cmd, check=False)
        sys.exit(result.returncode)
    except Exception as e:
        click.echo(f"{Colors.RED}✗{Colors.NC} Failed to run sops-diff: {e}", err=True)
        sys.exit(1)
