#!/usr/bin/env python3

"""
itsup sops-key command

Generate or rotate SOPS encryption keys.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

import click

logger = logging.getLogger(__name__)


class Colors:
    """ANSI color codes for terminal output"""

    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    NC = "\033[0m"  # No Color


def _check_age_installed() -> bool:
    """Check if age is installed."""
    try:
        subprocess.run(
            ["age", "--version"],
            capture_output=True,
            check=True,
            timeout=5
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


@click.command()
@click.option("--rotate", is_flag=True, help="Rotate existing key and re-encrypt all secrets")
def sops_key(rotate: bool):
    """🔑 Generate or rotate SOPS encryption key

    Creates a new age encryption key for SOPS at ~/.config/sops/age/keys.txt
    Automatically updates secrets/.sops.yaml with the new public key

    With --rotate: Backs up old key + re-encrypts all secrets with new key

    \b
    Examples:
        itsup sops-key              # Generate new key + update .sops.yaml
        itsup sops-key --rotate     # Rotate key + re-encrypt all secrets
    """
    if not _check_age_installed():
        click.echo(f"{Colors.RED}✗{Colors.NC} age is not installed", err=True)
        click.echo()
        click.echo("Install age:")
        click.echo("  macOS:   brew install age")
        click.echo("  Linux:   sudo apt-get install age")
        click.echo()
        sys.exit(1)

    # Key paths
    keys_dir = Path.home() / ".config" / "sops" / "age"
    key_file = keys_dir / "keys.txt"

    # Check if key already exists
    if key_file.exists() and not rotate:
        click.echo(f"{Colors.YELLOW}⚠{Colors.NC} SOPS key already exists at {key_file}")
        click.echo()
        if not click.confirm("Overwrite existing key?", default=False):
            click.echo()
            click.echo("Cancelled. Use --rotate to back up the old key first.")
            sys.exit(0)

    # Rotate: backup existing key
    if rotate and key_file.exists():
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = keys_dir / f"keys.txt.backup.{timestamp}"

        click.echo(f"{Colors.BLUE}🔄 Rotating SOPS key...{Colors.NC}")
        key_file.rename(backup_file)
        click.echo(f"{Colors.GREEN}✓{Colors.NC} Backed up old key to {backup_file.name}")
        click.echo()

    # Create keys directory if needed
    keys_dir.mkdir(parents=True, exist_ok=True)

    # Generate new key
    click.echo(f"{Colors.BLUE}🔑 Generating new age encryption key...{Colors.NC}")

    try:
        result = subprocess.run(
            ["age-keygen", "-o", str(key_file)],
            capture_output=True,
            check=True,
            text=True
        )

        # Extract public key from output
        public_key = None
        for line in result.stderr.splitlines():
            if line.startswith("Public key:"):
                public_key = line.split(":", 1)[1].strip()
                break

        click.echo(f"{Colors.GREEN}✓{Colors.NC} Generated new key at {key_file}")

        # Set permissions
        key_file.chmod(0o600)
        click.echo(f"{Colors.GREEN}✓{Colors.NC} Set permissions to 600")

        click.echo()
        click.echo("=" * 60)
        click.echo(f"{Colors.BLUE}Public Key:{Colors.NC}")
        click.echo()
        click.echo(f"  {Colors.GREEN}{public_key}{Colors.NC}")
        click.echo()
        click.echo("=" * 60)
        click.echo()

        # Auto-update .sops.yaml
        secrets_dir = Path("secrets")
        sops_yaml = secrets_dir / ".sops.yaml"

        if secrets_dir.exists():
            click.echo(f"{Colors.BLUE}📝 Updating .sops.yaml with new public key...{Colors.NC}")

            # Create or update .sops.yaml
            sops_config = f"""creation_rules:
  - age: {public_key}
"""
            sops_yaml.write_text(sops_config)
            click.echo(f"{Colors.GREEN}✓{Colors.NC} Updated {sops_yaml}")
            click.echo()
        else:
            click.echo(f"{Colors.YELLOW}⚠{Colors.NC} secrets/ directory not found")
            click.echo()
            click.echo("Manual .sops.yaml configuration:")
            click.echo()
            click.echo("     creation_rules:")
            click.echo(f"       - age: {public_key}")
            click.echo()

        # Show next steps
        click.echo("Next steps:")
        click.echo()
        if secrets_dir.exists() and sops_yaml.exists():
            click.echo("  1. Commit .sops.yaml:")
            click.echo("     itsup commit")
            click.echo()
        else:
            click.echo("  1. Create secrets/ directory and .sops.yaml:")
            click.echo("     mkdir -p secrets")
            click.echo("     cat > secrets/.sops.yaml <<EOF")
            click.echo("     creation_rules:")
            click.echo(f"       - age: {public_key}")
            click.echo("     EOF")
            click.echo()
            click.echo("  2. Commit .sops.yaml:")
            click.echo("     itsup commit")
            click.echo()

        if rotate:
            # Auto re-encrypt all secrets with new key
            click.echo()
            click.echo(f"{Colors.BLUE}🔄 Re-encrypting all secrets with new key...{Colors.NC}")
            click.echo()

            secrets_dir = Path("secrets")
            if not secrets_dir.exists():
                click.echo(f"{Colors.YELLOW}⚠{Colors.NC} secrets/ directory not found, skipping re-encryption")
                return

            encrypted_files = list(secrets_dir.glob("*.enc.txt"))
            if not encrypted_files:
                click.echo(f"{Colors.YELLOW}⚠{Colors.NC} No encrypted secrets found, skipping re-encryption")
                return

            # Step 1: Decrypt all with old key (from backup)
            click.echo("  1. Decrypting with old key...")
            backup_key_files = sorted(keys_dir.glob("keys.txt.backup.*"))
            if not backup_key_files:
                click.echo(f"{Colors.RED}✗{Colors.NC} No backup key found, cannot decrypt", err=True)
                click.echo("  Manually decrypt with old key before rotating")
                sys.exit(1)

            old_key_file = backup_key_files[-1]  # Most recent backup

            # Temporarily use old key for decryption
            decrypted = []
            for enc_file in encrypted_files:
                plaintext_file = enc_file.parent / enc_file.name.replace(".enc.txt", ".txt")
                try:
                    # Use old key explicitly
                    env = os.environ.copy()
                    env["SOPS_AGE_KEY_FILE"] = str(old_key_file)

                    with open(plaintext_file, 'w') as outfile:
                        subprocess.run(
                            ["sops", "-d", str(enc_file)],
                            stdout=outfile,
                            env=env,
                            check=True,
                            text=True
                        )
                    decrypted.append(plaintext_file)
                    click.echo(f"     ✓ Decrypted {enc_file.name}")
                except subprocess.CalledProcessError as e:
                    click.echo(f"{Colors.RED}✗{Colors.NC} Failed to decrypt {enc_file.name}: {e}", err=True)

            if not decrypted:
                click.echo(f"{Colors.RED}✗{Colors.NC} No files decrypted, aborting", err=True)
                sys.exit(1)

            click.echo()
            click.echo("  2. Re-encrypting with new key...")

            # Step 2: Re-encrypt all with new key
            re_encrypted = []
            for plaintext_file in decrypted:
                enc_file = plaintext_file.parent / plaintext_file.name.replace(".txt", ".enc.txt")
                try:
                    # New key is now active
                    with open(enc_file, 'w') as outfile:
                        subprocess.run(
                            ["sops", "-e", str(plaintext_file)],
                            stdout=outfile,
                            check=True,
                            text=True
                        )
                    # Delete plaintext
                    plaintext_file.unlink()
                    re_encrypted.append(enc_file)
                    click.echo(f"     ✓ Re-encrypted {enc_file.name}")
                except subprocess.CalledProcessError as e:
                    click.echo(f"{Colors.RED}✗{Colors.NC} Failed to re-encrypt {plaintext_file.name}: {e}", err=True)

            click.echo()
            if len(re_encrypted) == len(encrypted_files):
                click.echo(f"{Colors.GREEN}✅ All secrets re-encrypted with new key!{Colors.NC}")
            else:
                click.echo(f"{Colors.YELLOW}⚠{Colors.NC} Only {len(re_encrypted)}/{len(encrypted_files)} secrets re-encrypted")

            click.echo()
            click.echo("Final step:")
            click.echo()
            click.echo("  Commit the changes (auto-detects rotation):")
            click.echo("     itsup commit")
            click.echo()

        else:
            click.echo("  2. Create and encrypt your first secret:")
            click.echo("     itsup edit-secret itsup")
            click.echo()

    except subprocess.CalledProcessError as e:
        click.echo(f"{Colors.RED}✗{Colors.NC} Failed to generate key: {e}", err=True)
        if e.stderr:
            click.echo(e.stderr, err=True)
        sys.exit(1)
