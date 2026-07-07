#!/usr/bin/env python3

"""
itsup encrypt command

Encrypt plaintext secrets using SOPS.
"""

import sys

import click

from commands.common import fail, ok, warn
from lib.paths import root as install_root
from lib.sops import encrypt_file, is_sops_available


@click.command()
@click.argument("name", required=False)
@click.option("--delete", is_flag=True, help="Delete plaintext files after encryption")
@click.option("--force", is_flag=True, help="Force re-encryption even if content unchanged")
def encrypt(name: str, delete: bool, force: bool) -> None:
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

    # Find files to encrypt
    if name:
        # Encrypt specific file
        plaintext_files = [secrets_dir / f"{name}.txt"]
        if not plaintext_files[0].exists():
            fail(f"File not found: secrets/{name}.txt")
            sys.exit(1)
    else:
        # Encrypt all .txt files (exclude .enc.txt)
        plaintext_files = [f for f in secrets_dir.glob("*.txt") if not f.name.endswith(".enc.txt")]
        if not plaintext_files:
            warn("No plaintext secrets found in secrets/")
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
                click.echo(f"  {click.style('↳', fg='yellow')} Deleted {plaintext_path.name}")
        else:
            failed_files.append(plaintext_path.name)

    click.echo()

    # Summary
    if failed_files:
        fail(f"Failed to encrypt: {', '.join(failed_files)}")
        sys.exit(1)
    else:
        if encrypted_count > 0:
            ok(f"Encrypted {encrypted_count} file(s)")
        if skipped_count > 0:
            ok(f"Skipped {skipped_count} file(s) (unchanged)")

        if not delete:
            click.echo()
            warn("Plaintext files still exist!")
            click.echo("  To delete plaintext after verification:")
            click.echo("    itsup encrypt --delete")
