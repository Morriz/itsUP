#!/usr/bin/env python3

"""
itsup encrypt command

Encrypt plaintext secrets using SOPS.
"""

import sys

import click

from commands.common import fail, ok, warn
from lib.paths import display_path, secret_file, secrets_dir
from lib.sops import encrypt_plaintext_secrets, is_sops_available


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

    if not secrets_dir().exists():
        fail(f"Secrets directory not found: {display_path(secrets_dir())}")
        sys.exit(1)

    # Pre-check existence so a missing NAME fails before encryption runs
    if name:
        plaintext_path = secret_file(name, encrypted=False)
        if not plaintext_path.exists():
            fail(f"File not found: {display_path(plaintext_path)}")
            sys.exit(1)
    else:
        plaintext_files = [f for f in secrets_dir().glob("*.txt") if not f.name.endswith(".enc.txt")]
        if not plaintext_files:
            warn(f"No plaintext secrets found in {display_path(secrets_dir())}")
            return

    click.echo("Encrypting secrets...")
    click.echo()

    result = encrypt_plaintext_secrets(secrets_dir(), name=name, delete=delete, force=force)

    if delete:
        for plaintext_path in result.encrypted + result.skipped:
            click.echo(f"  {click.style('↳', fg='yellow')} Deleted {plaintext_path.name}")

    click.echo()

    # Summary
    if result.failed:
        fail(f"Failed to encrypt: {', '.join(p.name for p in result.failed)}")
        sys.exit(1)
    else:
        if result.encrypted:
            ok(f"Encrypted {len(result.encrypted)} file(s)")
        if result.skipped:
            ok(f"Skipped {len(result.skipped)} file(s) (unchanged)")

        if not delete:
            click.echo()
            warn("Plaintext files still exist!")
            click.echo("  To delete plaintext after verification:")
            click.echo("    itsup encrypt --delete")
