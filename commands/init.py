#!/usr/bin/env python3
"""Initialize new itsUP installation from samples"""

import logging
import shutil
from pathlib import Path

import click

logger = logging.getLogger(__name__)


@click.command()
@click.option("--non-interactive", is_flag=True, help="Skip prompts")
def init(non_interactive: bool) -> int:
    """
    Initialize new installation from samples

    Copies sample files to create initial configuration
    """
    click.echo("itsUP Initialization")
    click.echo("=" * 50)

    # Check if already initialized
    if Path("projects/traefik.yml").exists():
        click.echo("✗ Already initialized: projects/traefik.yml exists", err=True)
        click.echo("\nIf you want to re-initialize, first backup/remove projects/traefik.yml")
        return 1

    # Check submodules exist
    if not Path("projects/.git").exists():
        click.echo("✗ projects/ submodule not initialized", err=True)
        click.echo("Run: git submodule update --init --recursive")
        return 1

    if not Path("secrets/.git").exists():
        click.echo("⚠ secrets/ submodule not initialized")
        click.echo("Continuing without secrets submodule...")

    # Copy samples → destinations
    copies = [
        ("samples/env", ".env"),
        ("samples/traefik.yml", "projects/traefik.yml"),
        ("samples/secrets/global.txt", "secrets/global.txt"),
    ]

    for src, dst in copies:
        src_path = Path(src)
        dst_path = Path(dst)

        if not src_path.exists():
            click.echo(f"⚠ Sample not found: {src}")
            continue

        # Create parent directory
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy file
        shutil.copy2(src_path, dst_path)
        click.echo(f"✓ Copied {src} → {dst}")

    # Show next steps
    click.echo("\n" + "=" * 50)
    click.echo("✓ Initialization complete!\n")
    click.echo("Next steps:")
    click.echo("\n1. Edit .env:")
    click.echo("   - Set ITSUP_ROOT to absolute path of this directory")
    click.echo("\n2. Edit projects/traefik.yml:")
    click.echo("   - Change domain_suffix to your domain")
    click.echo("   - Adjust trusted_ips for your network")
    click.echo("   - Configure middleware settings")
    click.echo("\n3. Edit secrets/global.txt:")
    click.echo("   - Fill in LETSENCRYPT_EMAIL")
    click.echo("   - Generate TRAEFIK_ADMIN (htpasswd -nb admin password)")
    click.echo("   - Add CROWDSEC_API_KEY and other secrets")
    click.echo("\n4. Encrypt secrets:")
    click.echo("   cd secrets && sops -e global.txt > global.enc.txt")
    click.echo("\n5. Commit to git:")
    click.echo("   cd projects && git add traefik.yml && git commit -m 'Initial config'")
    click.echo("   cd ../secrets && git add global.enc.txt && git commit -m 'Initial secrets'")
    click.echo("\n6. Deploy:")
    click.echo("   ./itsup apply")

    return 0
