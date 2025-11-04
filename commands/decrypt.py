#!/usr/bin/env python3

"""
itsup decrypt command

Decrypt SOPS-encrypted secrets for editing.
"""

import logging
import sys
from pathlib import Path

import click

from lib.sops import decrypt_file, is_sops_available

logger = logging.getLogger(__name__)


class Colors:
    """ANSI color codes for terminal output"""

    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    NC = "\033[0m"  # No Color


@click.command()
@click.argument("name", required=False)
def decrypt(name: str):
    """🔓 Decrypt secrets for editing [NAME]

    Decrypts SOPS-encrypted *.enc.txt files to plaintext *.txt files.

    ⚠️  SECURITY WARNING: Plaintext files remain on disk until re-encrypted!
    For secure editing, use 'itsup edit-secret' instead (auto-cleanup).

    \b
    Examples:
        itsup decrypt               # Decrypt all secrets/*.enc.txt files
        itsup decrypt itsup         # Decrypt only itsup.enc.txt
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

    # Find files to decrypt
    if name:
        # Decrypt specific file
        encrypted_files = [secrets_dir / f"{name}.enc.txt"]
        if not encrypted_files[0].exists():
            click.echo(f"{Colors.RED}✗{Colors.NC} File not found: secrets/{name}.enc.txt", err=True)
            sys.exit(1)
    else:
        # Decrypt all .enc.txt files
        encrypted_files = list(secrets_dir.glob("*.enc.txt"))
        if not encrypted_files:
            click.echo(f"{Colors.YELLOW}⚠{Colors.NC} No encrypted secrets found in secrets/")
            return

    click.echo("Decrypting secrets...")
    click.echo()

    success_count = 0
    failed_files = []

    for encrypted_path in encrypted_files:
        # Remove .enc from .enc.txt to get .txt
        plaintext_path = encrypted_path.parent / encrypted_path.name.replace(".enc.txt", ".txt")

        if decrypt_file(encrypted_path, plaintext_path):
            success_count += 1
        else:
            failed_files.append(encrypted_path.name)

    click.echo()

    # Summary
    if failed_files:
        click.echo(f"{Colors.RED}✗{Colors.NC} Failed to decrypt: {', '.join(failed_files)}", err=True)
        sys.exit(1)
    else:
        click.echo(f"{Colors.GREEN}✓{Colors.NC} Decrypted {success_count} file(s)")
        click.echo()
        click.echo(f"{Colors.YELLOW}⚠  SECURITY WARNING:{Colors.NC}")
        click.echo("   Plaintext secrets are now on disk and will persist until re-encrypted!")
        click.echo()
        click.echo("   Re-encrypt after editing:")
        click.echo("     itsup encrypt --delete")
        click.echo()
        click.echo("   Or use secure editing (recommended):")
        click.echo("     itsup edit-secret <name>  # Auto-cleanup")
