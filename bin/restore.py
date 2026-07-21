#!/usr/bin/env python3
"""Bare restore dispatcher — download a backup generation from S3 and restore it.

Not an itsup subcommand by design: restore is destructive, so it ships as a
standalone guarded dispatcher. Every restore is gated behind an unconditional
confirmation prompt (it does NOT try to detect whether data exists — it always
asks); bypass with -y/--yes for automation.

Usage:
  bin/restore.py <target> [--from <s3-key>] [--yes] [--list]
    target   a project name | 'all' (whole stack) | 'proxy' (proxy state)
    --from   S3 archive key to restore (default: the latest generation)
    --yes    skip the confirmation prompt (non-interactive)
    --list   list available archive generations and exit
"""

# Re-exec under the project venv so direct invocation works from any interpreter.
import os as _os
import sys as _sys

_VENV = _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".venv"))
_VENV_PYTHON = _os.path.join(_VENV, "bin", "python")
if (
    __name__ == "__main__"
    and _os.path.exists(_VENV_PYTHON)
    and _os.path.realpath(_sys.prefix) != _os.path.realpath(_VENV)
):
    _os.execv(_VENV_PYTHON, [_VENV_PYTHON, _os.path.abspath(__file__), *_sys.argv[1:]])

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

# Add parent directory to path to import lib modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bin.backup import DB_FILE, build_s3_client
from lib.data import get_env_with_secrets, load_project_backup_config, resolve_backup_adapter
from lib.paths import root

PROXY_TARGET = "proxy"
ALL_TARGET = "all"


def list_generations(s3_client: Any, bucket: str) -> list[str]:
    """Return archive generation keys (itsup.tar.gz.<ts>), newest first."""
    response = s3_client.list_objects_v2(Bucket=bucket)
    prefix = f"{DB_FILE}."
    keys = [obj["Key"] for obj in response.get("Contents", []) if obj["Key"].startswith(prefix)]
    keys.sort(reverse=True)
    return keys


def resolve_key(s3_client: Any, bucket: str, requested: str | None) -> str:
    """Resolve the archive key to restore: the requested one, or the latest."""
    generations = list_generations(s3_client, bucket)
    if requested:
        if requested not in generations:
            print(f"Error: archive '{requested}' not found in bucket. Available: {generations}", file=sys.stderr)
            sys.exit(1)
        return requested
    if not generations:
        print("Error: no backup generations found in bucket.", file=sys.stderr)
        sys.exit(1)
    return generations[0]


def confirm(target: str, key: str, assume_yes: bool) -> None:
    """Unconditional overwrite guard. Aborts unless the operator confirms."""
    if assume_yes:
        return
    print(f"About to restore '{target}' from '{key}'.")
    print("This OVERWRITES existing data and cannot be undone.")
    answer = input("Continue? [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        print("Aborted.")
        sys.exit(1)


def download_and_extract(s3_client: Any, bucket: str, key: str, staging: Path) -> None:
    """Download the archive generation and extract it into the staging dir."""
    print(f"Downloading {key} ...")
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        archive_path = tmp.name
    try:
        s3_client.download_file(bucket, key, archive_path)
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=staging, filter="data")
    finally:
        os.remove(archive_path)


def restore_proxy(staging: Path) -> None:
    """Replace proxy/ with the archived proxy state."""
    src = staging / "proxy"
    if not src.is_dir():
        print("Warning: archive has no proxy/ state — nothing to restore.", file=sys.stderr)
        return
    dest = root() / "proxy"
    print(f"Restoring proxy state -> {dest}")
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def restore_project(staging: Path, project: str) -> None:
    """Restore one project: adapter restore into the running instance, or a
    filesystem extract for a non-adapter project."""
    src = staging / "upstream" / project
    if not src.is_dir():
        print(f"Warning: archive has no upstream/{project} — nothing to restore.", file=sys.stderr)
        return

    config = load_project_backup_config(project)
    dest = root() / "upstream" / project

    if config is not None and config.adapter is not None:
        # Adapter-backed: stage the dump on disk, then load it into the live engine.
        adapter = resolve_backup_adapter(project, config.adapter)
        if adapter is None:
            print(f"Error: no adapter '{config.adapter}' for project '{project}'", file=sys.stderr)
            sys.exit(1)
        backup_src = src / "_backup"
        if not backup_src.is_dir():
            print(f"Error: archive has no dump at upstream/{project}/_backup", file=sys.stderr)
            sys.exit(1)
        dest_backup = dest / "_backup"
        dest.mkdir(parents=True, exist_ok=True)
        if dest_backup.exists():
            shutil.rmtree(dest_backup)
        shutil.copytree(backup_src, dest_backup)
        print(f"Restoring '{project}' into the running instance via adapter '{config.adapter}'")
        subprocess.run(
            [str(adapter), "restore", str(dest)],
            env=get_env_with_secrets(project),
            check=True,
        )
    else:
        # Non-adapter: filesystem extract of the whole project tree.
        print(f"Restoring '{project}' as a filesystem extract -> {dest}")
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)


def restore_all(staging: Path) -> None:
    """Restore every project found in the archive, plus proxy state."""
    upstream = staging / "upstream"
    if upstream.is_dir():
        for child in sorted(upstream.iterdir()):
            if child.is_dir():
                restore_project(staging, child.name)
    restore_proxy(staging)


def run_restore(target: str, key: str, s3_client: Any, bucket: str) -> None:
    """Download, extract, and route the restore to the chosen target."""
    with tempfile.TemporaryDirectory() as staging_str:
        staging = Path(staging_str)
        download_and_extract(s3_client, bucket, key, staging)
        if target == PROXY_TARGET:
            restore_proxy(staging)
        elif target == ALL_TARGET:
            restore_all(staging)
        else:
            restore_project(staging, target)
    print("Restore complete.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Restore a backup generation from S3.")
    parser.add_argument("target", help="project name | 'all' | 'proxy'")
    parser.add_argument("--from", dest="from_key", default=None, help="S3 archive key (default: latest)")
    parser.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    parser.add_argument("--list", action="store_true", help="list archive generations and exit")
    args = parser.parse_args(argv)

    s3_client, bucket = build_s3_client()

    if args.list:
        for key in list_generations(s3_client, bucket):
            print(key)
        return

    key = resolve_key(s3_client, bucket, args.from_key)
    confirm(args.target, key, args.yes)
    run_restore(args.target, key, s3_client, bucket)


if __name__ == "__main__":
    main()
