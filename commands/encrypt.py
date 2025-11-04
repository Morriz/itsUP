#!/usr/bin/env python3

"""
itsup encrypt command

Encrypt plaintext secrets using SOPS.
"""

import logging
import sys
from pathlib import Path

import click

from lib.sops import encrypt_file, is_sops_available

logger = logging.getLogger(__name__)


class Colors:
    """ANSI color codes for terminal output"""

    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    NC = "\033[0m"  # No Color


@click.command()
@click.argument("name", required=False)
@click.option("--delete", is_flag=True, help="Delete plaintext files after encryption")
@click.option("--force", is_flag=True, help="Force re-encryption even if content unchanged")
def encrypt(name: str, delete: bool, force: bool):
    """🔒 Encrypt secrets with SOPS [NAME]

    Encrypts plaintext secrets/*.txt files using SOPS encryption.
    Encrypted files are saved as *.enc.txt

    By default, skips re-encryption if content is unchanged (avoids new git hashes).

    \b
    Examples:
        itsup encrypt               # Encrypt all secrets/*.txt files (skip unchanged)
        itsup encrypt itsup         # Encrypt only itsup.txt (skip if unchanged)
        itsup encrypt --force       # Force re-encrypt all (even unchanged files)
        itsup encrypt --delete      # Encrypt all and delete plaintext
    """
    if not is_sops_available():
        click.echo(f"{Colors.RED}✗{Colors.NC} SOPS is not installed", err=True)
        click.echo()
        click.echo("Install SOPS:")
        click.echo("  macOS:   brew install sops")
        click.echo("  Linux:   Download from https://github.com/mozilla/sops/releases")
        click.echo()
        sys.exit(1)

    root = Path(__file__).resolve().parent.parent
    secrets_dir = root / "secrets"

    if not secrets_dir.exists():
        click.echo(f"{Colors.RED}✗{Colors.NC} secrets/ directory not found", err=True)
        sys.exit(1)

    # Find files to encrypt
    if name:
        # Encrypt specific file
        plaintext_files = [secrets_dir / f"{name}.txt"]
        if not plaintext_files[0].exists():
            click.echo(f"{Colors.RED}✗{Colors.NC} File not found: secrets/{name}.txt", err=True)
            sys.exit(1)
    else:
        # Encrypt all .txt files (exclude .enc.txt)
        plaintext_files = [f for f in secrets_dir.glob("*.txt") if not f.name.endswith(".enc.txt")]
        if not plaintext_files:
            click.echo(f"{Colors.YELLOW}⚠{Colors.NC} No plaintext secrets found in secrets/")
            return

    click.echo("Encrypting secrets...")
    click.echo()

    encrypted_count = 0
    skipped_count = 0
    failed_files = []

    for plaintext_path in plaintext_files:
        encrypted_path = plaintext_path.with_suffix(".enc.txt")

        success, was_encrypted = encrypt_file(plaintext_path, encrypted_path, force=force)
        if success:
            if was_encrypted:
                encrypted_count += 1
            else:
                skipped_count += 1

            # Optionally delete plaintext
            if delete:
                plaintext_path.unlink()
                click.echo(f"  {Colors.YELLOW}↳{Colors.NC} Deleted {plaintext_path.name}")
        else:
            failed_files.append(plaintext_path.name)

    click.echo()

    # Summary
    if failed_files:
        click.echo(f"{Colors.RED}✗{Colors.NC} Failed to encrypt: {', '.join(failed_files)}", err=True)
        sys.exit(1)
    else:
        if encrypted_count > 0:
            click.echo(f"{Colors.GREEN}✓{Colors.NC} Encrypted {encrypted_count} file(s)")
        if skipped_count > 0:
            click.echo(f"{Colors.GREEN}✓{Colors.NC} Skipped {skipped_count} file(s) (unchanged)")

        if not delete:
            click.echo()
            click.echo(f"{Colors.YELLOW}⚠{Colors.NC} Plaintext files still exist!")
            click.echo("  To delete plaintext after verification:")
            click.echo("    itsup encrypt --delete")
