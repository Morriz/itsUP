"""itsUP CLI - Command-line interface for itsUP management.

The single source of the click command group. ``main()`` is the console-script
target (``pyproject.toml`` ``[project.scripts] itsup = "itsup.cli:main"``).
"""

import os

import click
from instrukt_ai_logging import configure_logging

from commands.apply import apply
from commands.commit import commit
from commands.create import create
from commands.decrypt import decrypt
from commands.diff_secrets import diff_secrets
from commands.dns import dns
from commands.down import down
from commands.edit_secret import edit_secret
from commands.encrypt import encrypt
from commands.init import init
from commands.migrate import migrate_cmd
from commands.monitor import monitor
from commands.projects import projects
from commands.proxy import proxy
from commands.pull import pull
from commands.run import run
from commands.sops_key import sops_key
from commands.status import status
from commands.svc import svc
from commands.validate import validate
from lib.host_gate import require_host

HOST_ONLY = frozenset({"run", "apply", "down", "dns", "proxy", "svc", "monitor"})


@click.group(context_settings={"allow_interspersed_args": False, "help_option_names": ["-h", "--help"]})
@click.version_option("2.1.1", "-V", "--version", prog_name="itsup")
@click.option("--verbose", "-v", count=True, help="Verbosity: -v (DEBUG), -vv (TRACE)", is_eager=True)
@click.pass_context
def cli(ctx: click.Context, verbose: int) -> None:
    """itsUP - Infrastructure management CLI

    \b
    Agent GitOps workflow:
      itsup pull                    # Sync projects/ and secrets/ before editing
      itsup projects [NAME]         # Discover project names, or a project's files
      <edit files with your own tools>
      itsup decrypt NAME            # Decrypt a secret to plaintext for editing
      itsup encrypt NAME --delete   # Re-encrypt and remove plaintext
      itsup commit                  # Auto-encrypts remaining plaintext, commits, pushes

    \b
    itsup edit-secret is interactive and human-only; agents use the round
    trip above instead.
    """
    # itsup is a user-invoked, intent-bearing tool — every git subprocess it
    # spawns (commit/pull/status/etc.) is sanctioned. Set the bypass once here
    # so the TeleClaude git wrapper passes our calls through, instead of
    # threading env= through every subprocess.run([...,"git",...]) site.
    os.environ["TELECLAUDE_TRUSTED_TOOL"] = "1"

    # Map verbosity count to log levels (CLI ignores LOG_LEVEL env var)
    # 0 = INFO (default - show info and errors)
    # 1 = DEBUG (-v)
    # 2+ = TRACE (-vv)
    if verbose == 0:
        level = "INFO"
    elif verbose == 1:
        level = "DEBUG"
    else:  # 2+
        level = "TRACE"

    os.environ["ITSUP_LOG_LEVEL"] = level
    configure_logging("itsup")

    if ctx.invoked_subcommand in HOST_ONLY:
        require_host(ctx.invoked_subcommand)


# Register commands
cli.add_command(init)
cli.add_command(create)
cli.add_command(pull)
cli.add_command(status)
cli.add_command(commit)
cli.add_command(run)
cli.add_command(down)
cli.add_command(dns)
cli.add_command(proxy)
cli.add_command(apply)
cli.add_command(svc)
cli.add_command(validate)
cli.add_command(migrate_cmd, name="migrate")
cli.add_command(monitor)
cli.add_command(encrypt)
cli.add_command(decrypt)
cli.add_command(diff_secrets)
cli.add_command(edit_secret)
cli.add_command(sops_key)
cli.add_command(projects)


def main() -> None:
    """Console-script entry point."""
    cli.main()
