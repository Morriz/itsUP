#!/usr/bin/env python3

"""
itsup edit-secret command

Edit encrypted secrets seamlessly (decrypts, opens editor, re-encrypts).
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import click

from commands.common import fail, is_interactive, ok, warn
from lib.paths import display_path, secret_file, secrets_dir
from lib.sops import decrypt_file, encrypt_file, is_sops_available


@click.command()
@click.argument("name", required=True)
def edit_secret(name: str) -> None:
    """✏️  Edit encrypted secret seamlessly NAME (interactive, human-only)

    Ultimate UX: Decrypts secret, opens in editor, re-encrypts on save.
    You never touch the encrypted file directly! Requires a real terminal —
    agents use the non-interactive decrypt/encrypt/commit round trip instead.

    \b
    Examples:
        itsup edit-secret itsup         # Edit itsup.enc.txt
        itsup edit-secret my-project    # Edit my-project.enc.txt
    """
    if not is_interactive():
        fail("itsup edit-secret is interactive and human-only")
        click.echo()
        click.echo("Non-interactive round trip:")
        click.echo(f"  itsup decrypt {name}")
        click.echo(f"  <edit {display_path(secret_file(name, encrypted=False))}>")
        click.echo(f"  itsup encrypt {name} --delete")
        click.echo("  itsup commit")
        sys.exit(1)

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

    encrypted_path = secret_file(name, encrypted=True)
    plaintext_path = secret_file(name, encrypted=False)

    # Check if encrypted file exists
    if not encrypted_path.exists():
        fail(f"Encrypted file not found: {display_path(encrypted_path)}")
        click.echo()
        click.echo("To create a new secret:")
        click.echo(f"  1. edit {display_path(plaintext_path)}")
        click.echo(f"  2. itsup encrypt {name}")
        sys.exit(1)

    # Get editor with fallback priority: vim > nano > vi > $EDITOR
    # This ensures we use a blocking terminal editor, not GUI editors like 'code'
    current_editor = os.environ.get("EDITOR", "")

    # Find first available editor (prefer terminal editors over GUI)
    editor = None
    for try_editor in ["nano", "vim", "vi", current_editor]:
        if try_editor and subprocess.run(["which", try_editor], capture_output=True).returncode == 0:
            editor = try_editor
            break

    if not editor:
        fail("No editor found")
        click.echo("Install either nano, vim, or vi")
        sys.exit(1)

    click.echo(f"Editing {name}.enc.txt...")
    click.echo()

    # Create temp file for editing
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        # Step 1: Decrypt to temp file
        click.echo("  🔓 Decrypting...")
        if not decrypt_file(encrypted_path, tmp_path):
            fail("Failed to decrypt")
            sys.exit(1)

        # Get original modification time
        original_mtime = tmp_path.stat().st_mtime

        # Step 2: Open in editor
        click.echo(f"  ✏️  Opening in {editor}...")

        subprocess.run([editor, str(tmp_path)], check=True)

        # Check if file was modified
        new_mtime = tmp_path.stat().st_mtime
        if new_mtime == original_mtime:
            click.echo()
            warn("No changes made")
            return

        # Step 3: Re-encrypt
        click.echo("  🔒 Re-encrypting...")
        success, _ = encrypt_file(tmp_path, encrypted_path)
        if not success:
            fail("Failed to re-encrypt")
            click.echo(f"  Plaintext saved at: {tmp_path}")
            sys.exit(1)

        # Delete plaintext if it was created in secrets/
        if plaintext_path.exists():
            plaintext_path.unlink()

        click.echo()
        ok("Secret updated and re-encrypted")
        click.echo()
        click.echo("Next steps:")
        click.echo("  itsup commit")

    except subprocess.CalledProcessError as e:
        fail(f"Editor failed: {e}")
        sys.exit(1)

    finally:
        # Cleanup temp file
        if tmp_path.exists():
            tmp_path.unlink()
