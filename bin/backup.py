import argparse
import os
import subprocess
import sys
import tarfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

import boto3
import botocore.exceptions
from botocore.client import Config
from instrukt_ai_logging import configure_logging, get_logger

# Add parent directory to path to import lib modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.data import (
    BackupConfig,
    get_env_with_secrets,
    load_project_backup_config,
    load_secrets,
    resolve_backup_adapter,
)
from lib.paths import root

logger = get_logger("itsup.backup")

DB_FILE = "itsup.tar.gz"
STAGING_PREFIX = "_staging/"
VALIDATED_PREFIX = "_validated/"


def discover_backup_configs(upstream_dir: Path) -> dict[str, BackupConfig]:
    """Map each upstream project that carries a backup.yml to its BackupConfig.

    Anchored on the upstream tree because that is what gets archived: a project's
    adapter dump is written into upstream/<name>/_backup/ and its exclusion paths
    sit under upstream/<name>/.
    """
    configs: dict[str, BackupConfig] = {}
    for item in sorted(os.listdir(upstream_dir)):
        if not (upstream_dir / item).is_dir():
            continue
        config = load_project_backup_config(item)
        if config is not None:
            configs[item] = config
    return configs


def run_adapter_dump(adapter: Path, project: str, target: Path) -> None:
    """Run one adapter `dump` against the project's upstream dir (compose-exec)."""
    subprocess.run(
        [str(adapter), "dump", str(target)],
        env=get_env_with_secrets(project),
        check=True,
        capture_output=True,
        text=True,
    )


def run_adapter_dumps(configs: dict[str, BackupConfig], upstream_dir: Path) -> list[str]:
    """Run adapter dumps concurrently, returning the names of projects that failed.

    Partial availability over total failure: a dump that fails (container down,
    missing adapter, exec error) is logged and its project skipped — the run still
    archives every healthy project plus proxy state. The caller surfaces the
    partial result (non-zero exit + PARTIAL BACKUP summary); it is never silent.
    """
    jobs = {project: config for project, config in configs.items() if config.adapter}
    if not jobs:
        return []

    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=min(len(jobs), 8)) as executor:
        futures = {}
        for project, config in jobs.items():
            assert config.adapter is not None  # filtered above
            adapter = resolve_backup_adapter(project, config.adapter)
            if adapter is None:
                logger.error("backup: no adapter '%s' found for project '%s' — skipping", config.adapter, project)
                failed.append(project)
                continue
            futures[executor.submit(run_adapter_dump, adapter, project, upstream_dir / project)] = project

        for future in as_completed(futures):
            project = futures[future]
            try:
                future.result()
                print(f"Adapter dump complete: {project}")
            except subprocess.CalledProcessError as e:
                logger.error("backup: adapter dump failed for '%s' — skipping. stderr: %s", project, e.stderr)
                failed.append(project)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("backup: adapter dump errored for '%s' — skipping: %s", project, e)
                failed.append(project)

    return failed


def build_exclude_paths(configs: dict[str, BackupConfig], upstream_dir: Path) -> set[str]:
    """Derive the live-tar exclusion set from each project's backup.yml.

    A project with an adapter dump excludes its torn live data dir so the archive
    never carries a crash-inconsistent copy; an ephemeral store excludes its data
    with no dump at all. The exclusion is derived solely from the presence and
    `exclude` paths of backup.yml — there is no separately maintained list.
    """
    excludes: set[str] = set()
    for project, config in configs.items():
        for rel in config.exclude:
            excludes.add(os.path.normpath(str(upstream_dir / project / rel)))
    return excludes


def add_robust(tar: tarfile.TarFile, src: str, arcname: str, exclude_paths: set[str]) -> None:
    """Walk src and tar each entry, skipping excluded paths and vanished files.

    Containers actively writing to their volumes (notably redis with its
    `temp-NNN.rdb` snapshot files renamed atomically to dump.rdb) routinely
    cause `tar.add` to crash with FileNotFoundError when an enumerated entry
    is gone by the time tar opens it. We do the walk ourselves and add each
    entry non-recursively so one disappearing file only skips itself. Paths in
    `exclude_paths` (derived from backup.yml) are pruned entirely.
    """
    if os.path.normpath(src) in exclude_paths:
        print(f"  skip (excluded): {src}")
        return
    try:
        tar.add(src, arcname=arcname, recursive=False)
    except FileNotFoundError:
        print(f"  skip (vanished): {src}")
        return
    if not os.path.isdir(src):
        return
    try:
        entries = sorted(os.listdir(src))
    except FileNotFoundError:
        return
    for entry in entries:
        add_robust(tar, os.path.join(src, entry), os.path.join(arcname, entry), exclude_paths)


def create_archive(upstream_dir: Path, exclude_paths: set[str]) -> None:
    """Tar upstream/ (skipping excluded paths) plus proxy/ state into DB_FILE."""
    print(f"Creating backup archive: {DB_FILE}")
    with tarfile.open(DB_FILE, "w:gz") as tar:
        for item in sorted(os.listdir(upstream_dir)):
            item_path = str(upstream_dir / item)
            print(f"Adding to tarball: {item_path}")
            add_robust(tar, item_path, os.path.join("upstream", item), exclude_paths)

        # Proxy config + acme.json certificates survive total loss alongside upstream.
        proxy_dir = root() / "proxy"
        if proxy_dir.is_dir():
            print(f"Adding to tarball: {proxy_dir}")
            add_robust(tar, str(proxy_dir), "proxy", exclude_paths)
        else:
            print("No ./proxy directory — skipping proxy state")


def build_s3_client() -> tuple[Any, str]:
    """Build an S3 client + bucket from infra secrets (shared by backup/restore).

    Loads the AWS settings per-context via load_secrets() — the single boto3
    access pattern. Exits with a clear error when required secrets are missing.
    """
    secrets = load_secrets()

    required_secrets = [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_S3_HOST",
        "AWS_S3_REGION",
        "AWS_S3_BUCKET",
    ]

    missing = [key for key in required_secrets if key not in secrets]
    if missing:
        print(f"Error: Missing required secrets for S3 access: {', '.join(missing)}")
        print("Add to secrets/itsup.txt or secrets/itsup.enc.txt")
        sys.exit(1)

    aws_s3_host = secrets["AWS_S3_HOST"]
    # Format endpoint URL correctly
    if not aws_s3_host.startswith(("http://", "https://")):
        endpoint_url = f"https://{aws_s3_host}"
    else:
        endpoint_url = aws_s3_host

    print(
        f"AWS S3 Configuration: Host={aws_s3_host}, Region={secrets['AWS_S3_REGION']}, Bucket={secrets['AWS_S3_BUCKET']}"
    )
    print(f"Endpoint URL: {endpoint_url}")

    s3_client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=secrets["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=secrets["AWS_SECRET_ACCESS_KEY"],
        region_name=secrets["AWS_S3_REGION"],
        config=Config(signature_version="s3v4"),
    )
    return s3_client, secrets["AWS_S3_BUCKET"]


def _delete_staging_object(s3_client: Any, bucket: str, staging_key: str) -> None:
    """Best-effort cleanup for an upload that never became a generation."""
    try:
        s3_client.delete_object(Bucket=bucket, Key=staging_key)
    except Exception as error:  # pylint: disable=broad-exception-caught
        logger.error("backup: failed to clean staged upload '%s': %s", staging_key, error)


def prune_generations(s3_client: Any, bucket: str) -> None:
    """Keep ten generations, evicting unvalidated objects before validated ones."""
    response = s3_client.list_objects_v2(Bucket=bucket)
    keys = [obj["Key"] for obj in response.get("Contents", [])]
    generation_prefix = f"{DB_FILE}."
    generations = sorted((key for key in keys if key.startswith(generation_prefix)), reverse=True)
    validated = {
        key.removeprefix(VALIDATED_PREFIX) for key in keys if key.startswith(VALIDATED_PREFIX)
    }

    excess = len(generations) - 10
    if excess <= 0:
        return

    unvalidated = sorted(key for key in generations if key not in validated)
    validated_generations = sorted(key for key in generations if key in validated)
    for generation in (unvalidated + validated_generations)[:excess]:
        print(f"Deleting old backup: {generation}")
        s3_client.delete_object(Bucket=bucket, Key=generation)
        if generation in validated:
            s3_client.delete_object(Bucket=bucket, Key=f"{VALIDATED_PREFIX}{generation}")


def upload_to_s3() -> None:
    """Publish DB_FILE only after its staged S3 upload is complete."""
    print("Uploading backup to S3")
    s3_client, aws_s3_bucket = build_s3_client()

    # Generate a timestamped name for the new backup
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    new_backup_name = f"{DB_FILE}.{timestamp}"
    staging_key = f"{STAGING_PREFIX}{new_backup_name}"
    local_size = os.path.getsize(DB_FILE)

    print(f"Uploading staged backup: {staging_key}")
    try:
        with open(DB_FILE, "rb") as file_data:
            s3_client.upload_fileobj(file_data, aws_s3_bucket, staging_key)

        staged_size = s3_client.head_object(Bucket=aws_s3_bucket, Key=staging_key)["ContentLength"]
        if staged_size != local_size:
            logger.error(
                "backup: staged upload size mismatch for '%s': expected %s bytes, got %s",
                staging_key,
                local_size,
                staged_size,
            )
            print("Error: staged backup upload is incomplete; refusing to publish it.")
            _delete_staging_object(s3_client, aws_s3_bucket, staging_key)
            sys.exit(1)

        s3_client.copy(
            CopySource={"Bucket": aws_s3_bucket, "Key": staging_key},
            Bucket=aws_s3_bucket,
            Key=new_backup_name,
        )
        s3_client.put_object(Bucket=aws_s3_bucket, Key=f"{VALIDATED_PREFIX}{new_backup_name}", Body=b"")
        s3_client.delete_object(Bucket=aws_s3_bucket, Key=staging_key)
        prune_generations(s3_client, aws_s3_bucket)
        print("Backup completed successfully")
    except botocore.exceptions.ClientError as e:
        _delete_staging_object(s3_client, aws_s3_bucket, staging_key)
        print(f"AWS S3 Client Error: {e}")
        sys.exit(1)
    except botocore.exceptions.EndpointConnectionError as e:
        _delete_staging_object(s3_client, aws_s3_bucket, staging_key)
        print(f"Cannot connect to S3 endpoint: {e}")
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-exception-caught
        _delete_staging_object(s3_client, aws_s3_bucket, staging_key)
        logger.error("backup: staged publication failed for '%s': %s", staging_key, e)
        print(f"Error uploading to S3: {e}")
        sys.exit(1)
    finally:
        os.remove(DB_FILE)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run the full production backup. This script takes no arguments."
    )
    parser.parse_args(argv)

    os.environ.setdefault("ITSUP_LOG_LEVEL", os.getenv("LOG_LEVEL", "INFO"))
    configure_logging("itsup", source="backup")

    upstream_dir = root() / "upstream"
    if not upstream_dir.is_dir():
        print("Error: './upstream' directory not found.")
        sys.exit(1)

    configs = discover_backup_configs(upstream_dir)
    print(f"Projects with backup.yml: {sorted(configs)}")

    # Consistent dumps run before the tar so the archive captures them.
    failed_projects = run_adapter_dumps(configs, upstream_dir)

    exclude_paths = build_exclude_paths(configs, upstream_dir)
    print(f"Excluded paths: {sorted(exclude_paths)}")

    create_archive(upstream_dir, exclude_paths)
    upload_to_s3()

    if failed_projects:
        print(
            f"PARTIAL BACKUP: archived and uploaded healthy projects + proxy, but "
            f"{len(failed_projects)} adapter dump(s) failed and were skipped: "
            f"{', '.join(sorted(failed_projects))}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
