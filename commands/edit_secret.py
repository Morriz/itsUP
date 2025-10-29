#!/usr/bin/env python3

"""
itsup edit-secret command

Edit encrypted secrets seamlessly (decrypts, opens editor, re-encrypts).
"""

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import click

from lib.sops import decrypt_file, encrypt_file, is_sops_available

logger = logging.getLogger(__name__)


class Colors:
    """ANSI color codes for terminal output"""

    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    NC = "\033[0m"  # No Color


@click.command()
@click.argument("name", required=True)
def edit_secret(name: str):
    """✏️  Edit encrypted secret seamlessly NAME

    Ultimate UX: Decrypts secret, opens in editor, re-encrypts on save.
    You never touch the encrypted file directly!

    Examples:
        itsup edit-secret itsup         # Edit itsup.enc.txt
        itsup edit-secret my-project    # Edit my-project.enc.txt
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

    encrypted_path = secrets_dir / f"{name}.enc.txt"
    plaintext_path = secrets_dir / f"{name}.txt"

    # Check if encrypted file exists
    if not encrypted_path.exists():
        click.echo(f"{Colors.RED}✗{Colors.NC} Encrypted file not found: secrets/{name}.enc.txt", err=True)
        click.echo()
        click.echo(f"To create a new secret:")
        click.echo(f"  1. vim secrets/{name}.txt")
        click.echo(f"  2. itsup encrypt {name}")
        sys.exit(1)

    # Get editor (try $EDITOR, then common editors)
    editor = os.environ.get("EDITOR")
    if not editor:
        # Try common editors
        for try_editor in ["vim", "nano", "vi"]:
            try:
                subprocess.run(["which", try_editor], capture_output=True, check=True)
                editor = try_editor
                break
            except subprocess.CalledProcessError:
                continue

    if not editor:
        click.echo(f"{Colors.RED}✗{Colors.NC} No editor found", err=True)
        click.echo("Set EDITOR environment variable or install vim/nano")
        sys.exit(1)

    click.echo(f"Editing {name}.enc.txt...")
    click.echo()

    # Create temp file for editing
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        # Step 1: Decrypt to temp file
        click.echo(f"  🔓 Decrypting...")
        if not decrypt_file(encrypted_path, tmp_path):
            click.echo(f"{Colors.RED}✗{Colors.NC} Failed to decrypt", err=True)
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
            click.echo(f"{Colors.YELLOW}⚠{Colors.NC} No changes made")
            return

        # Step 3: Re-encrypt
        click.echo(f"  🔒 Re-encrypting...")
        success, _ = encrypt_file(tmp_path, encrypted_path)
        if not success:
            click.echo(f"{Colors.RED}✗{Colors.NC} Failed to re-encrypt", err=True)
            click.echo(f"  Plaintext saved at: {tmp_path}")
            sys.exit(1)

        # Delete plaintext if it was created in secrets/
        if plaintext_path.exists():
            plaintext_path.unlink()

        click.echo()
        click.echo(f"{Colors.GREEN}✓{Colors.NC} Secret updated and re-encrypted")
        click.echo()
        click.echo("Next steps:")
        click.echo("  itsup commit")

    except subprocess.CalledProcessError as e:
        click.echo(f"{Colors.RED}✗{Colors.NC} Editor failed: {e}", err=True)
        sys.exit(1)

    finally:
        # Cleanup temp file
        if tmp_path.exists():
            tmp_path.unlink()
