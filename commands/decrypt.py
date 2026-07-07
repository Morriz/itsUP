#!/usr/bin/env python3

"""
itsup decrypt command

Decrypt SOPS-encrypted secrets for editing.
"""

import sys

import click

from commands.common import fail, ok, warn
from lib.paths import root as install_root
from lib.sops import decrypt_file, is_sops_available


@click.command()
@click.argument("name", required=False)
def decrypt(name: str) -> None:
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
        fail("SOPS is not installed")
        click.echo()
        click.echo("Install SOPS:")
        click.echo("  macOS:   brew install sops")
        click.echo("  Linux:   Download from https://github.com/mozilla/sops/releases")
        click.echo()
        sys.exit(1)

    secrets_dir = install_root() / "secrets"

    if not secrets_dir.exists():
        fail("secrets/ directory not found")
        sys.exit(1)

    # Find files to decrypt
    if name:
        # Decrypt specific file
        encrypted_files = [secrets_dir / f"{name}.enc.txt"]
        if not encrypted_files[0].exists():
            fail(f"File not found: secrets/{name}.enc.txt")
            sys.exit(1)
    else:
        # Decrypt all .enc.txt files
        encrypted_files = list(secrets_dir.glob("*.enc.txt"))
        if not encrypted_files:
            warn("No encrypted secrets found in secrets/")
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
        fail(f"Failed to decrypt: {', '.join(failed_files)}")
        sys.exit(1)
    else:
        ok(f"Decrypted {success_count} file(s)")
        click.echo()
        warn("SECURITY WARNING:")
        click.echo("   Plaintext secrets are now on disk and will persist until re-encrypted!")
        click.echo()
        click.echo("   Re-encrypt after editing:")
        click.echo("     itsup encrypt --delete")
        click.echo()
        click.echo("   Or use secure editing (recommended):")
        click.echo("     itsup edit-secret <name>  # Auto-cleanup")
