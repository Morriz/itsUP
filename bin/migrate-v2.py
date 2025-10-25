#!.venv/bin/python
"""Migrate current V1 setup to V2 architecture by copying existing artifacts"""

import argparse
import logging
import os
import sys
import yaml
import shutil
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

from lib.logging_config import setup_logging
from lib.data import validate_db

logger = logging.getLogger(__name__)


def replace_secrets_with_vars(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively replace secret values with ${VAR} references"""
    # Load secrets map
    secrets = {}
    secrets_file = Path('secrets/global.txt')
    if secrets_file.exists():
        try:
            with open(secrets_file, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        secrets[value.strip()] = key.strip()
        except (IOError, PermissionError) as e:
            logger.warning(f"Could not read secrets file {secrets_file}: {e}")
            # Continue without secret replacement

    def replace_value(val):
        if isinstance(val, str) and val in secrets:
            return f"${{{secrets[val]}}}"
        return val

    def replace_dict(d):
        if isinstance(d, dict):
            return {k: replace_dict(v) for k, v in d.items()}
        elif isinstance(d, list):
            return [replace_dict(item) for item in d]
        else:
            return replace_value(d)

    return replace_dict(data)


def migrate_infrastructure(db: Dict[str, Any]) -> Dict[str, Any]:
    """Extract infrastructure config from db.yml → projects/traefik.yml"""

    # Extract infrastructure sections
    infra = {}

    # Copy relevant sections
    if 'domain_suffix' in db:
        infra['domain_suffix'] = db['domain_suffix']

    if 'letsencrypt' in db:
        infra['letsencrypt'] = db['letsencrypt']

    if 'trusted_ips' in db:
        infra['trusted_ips'] = db['trusted_ips']

    if 'traefik' in db:
        infra['traefik'] = db['traefik']

    if 'middleware' in db:
        infra['middleware'] = db['middleware']

    if 'plugins' in db:
        infra['plugins'] = db['plugins']

    if 'versions' in db:
        infra['versions'] = db['versions']

    # Replace secrets with ${VAR} references
    infra = replace_secrets_with_vars(infra)

    return infra


def migrate_project_traefik_config(project: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract traefik routing config from db.yml project

    Returns: traefik_config dict
    """
    name = project.get('name')
    if not name:
        raise ValueError("Project missing required 'name' field")

    # Build traefik.yml
    traefik = {
        'enabled': project.get('enabled', True),
        'ingress': []
    }

    for service in project.get('services', []):
        svc_host = service.get('host')
        if not svc_host:
            continue
        for ingress in service.get('ingress', []):
            if not ingress:
                continue

            traefik_ingress = {'service': svc_host}

            for key in ['domain', 'port', 'router', 'path_prefix', 'hostport', 'passthrough']:
                if key in ingress:
                    traefik_ingress[key] = ingress[key]

            if 'tls' in ingress and 'sans' in ingress['tls']:
                traefik_ingress['tls_sans'] = ingress['tls']['sans']

            traefik['ingress'].append(traefik_ingress)

    # Replace secrets with ${VAR} references
    traefik = replace_secrets_with_vars(traefik)

    return traefik


def check_file_exists(path: Path, force: bool) -> bool:
    """Check if file exists and return whether to proceed"""
    if path.exists() and not force:
        logger.error(f"File {path} already exists. Use --force to overwrite.")
        return False
    return True


def validate_project_name(name: str) -> str:
    """Validate and sanitize project name to prevent path traversal"""
    # Remove any path components (../, ./, /, etc.)
    sanitized = Path(name).name
    if sanitized != name:
        raise ValueError(
            f"Invalid project name '{name}'. "
            f"Project names cannot contain path separators or special path components."
        )
    if not sanitized or sanitized in ('.', '..'):
        raise ValueError(f"Invalid project name '{name}'")
    return sanitized


def main() -> int:
    """Main migration function. Returns exit code."""
    parser = argparse.ArgumentParser(
        description="Migrate V1 setup to V2 architecture (projects/ structure)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Run migration
  %(prog)s --dry-run          # Preview what would be migrated
  %(prog)s --force            # Overwrite existing files

This script:
  1. Validates db.yml before migration
  2. Creates db.yml.v1-backup (WARNING: contains plaintext secrets)
  3. Extracts infrastructure → projects/traefik.yml
  4. Copies upstream/{name}/docker-compose.yml → projects/{name}/docker-compose.yml
  5. Generates projects/{name}/traefik.yml from db.yml routing config
  6. Replaces secret values with ${VAR} references from secrets/global.txt
        """
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be migrated without writing files'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing files in projects/ directory'
    )

    args = parser.parse_args()

    try:
        # Validate db.yml first
        logger.info("Validating db.yml...")
        try:
            validate_db()
        except Exception as e:
            logger.error(f"db.yml validation failed: {e}")
            logger.error("Please fix db.yml before migrating")
            return 1

        # Load db.yml
        db_path = Path('db.yml')
        if not db_path.exists():
            logger.error("db.yml not found in current directory")
            logger.error("Please run this script from the project root")
            return 1

        logger.info("Loading db.yml...")
        try:
            with open(db_path, encoding='utf-8') as f:
                db = yaml.safe_load(f)
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse db.yml: {e}")
            return 1
        except (IOError, PermissionError) as e:
            logger.error(f"Failed to read db.yml: {e}")
            return 1

        if not isinstance(db, dict):
            logger.error("db.yml is not a valid dictionary")
            return 1

        # Check that upstream/ directory exists
        upstream_dir = Path('upstream')
        if not upstream_dir.exists():
            logger.error("upstream/ directory not found")
            logger.error("Please run 'bin/write-artifacts.py' first to generate V1 artifacts")
            return 1

        # Dry run mode
        if args.dry_run:
            logger.info("DRY RUN MODE - No files will be written")
            logger.info("")
            logger.info("Would create:")
            logger.info("  - db.yml.v1-backup")
            logger.info("  - projects/traefik.yml")
            for project in db.get('projects', []):
                name = project.get('name', '<missing>')
                try:
                    sanitized_name = validate_project_name(name)
                    upstream_compose = upstream_dir / sanitized_name / 'docker-compose.yml'
                    if upstream_compose.exists():
                        logger.info(f"  - projects/{sanitized_name}/docker-compose.yml (copied from upstream/)")
                    else:
                        logger.warning(f"  - projects/{sanitized_name}/docker-compose.yml (WARNING: upstream file not found)")
                    logger.info(f"  - projects/{sanitized_name}/traefik.yml")
                except ValueError as e:
                    logger.error(f"  - ERROR: {e}")
            return 0

        # Check if files exist
        backup_path = Path('db.yml.v1-backup')
        traefik_path = Path('projects/traefik.yml')

        if not check_file_exists(backup_path, args.force):
            return 1
        if not check_file_exists(traefik_path, args.force):
            return 1

        for project in db.get('projects', []):
            name = validate_project_name(project.get('name', ''))
            project_dir = Path('projects') / name
            if not check_file_exists(project_dir / 'docker-compose.yml', args.force):
                return 1
            if not check_file_exists(project_dir / 'traefik.yml', args.force):
                return 1

        # Create backup (WARNING: contains secrets in plaintext)
        logger.info("Creating backup...")
        logger.warning("WARNING: db.yml.v1-backup will contain secrets in plaintext")
        logger.warning("Keep this file secure and do not commit it to version control")
        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                yaml.dump(db, f)
        except (IOError, PermissionError) as e:
            logger.error(f"Failed to create backup: {e}")
            return 1

        logger.info("Migrating to V2 architecture...")
        logger.info("")

        # Ensure projects/ directory exists
        projects_dir = Path('projects')
        projects_dir.mkdir(exist_ok=True)

        # 1. Migrate infrastructure config
        logger.info("1. Extracting infrastructure config...")
        infra = migrate_infrastructure(db)

        try:
            with open(traefik_path, 'w', encoding='utf-8') as f:
                f.write("# Infrastructure configuration\n")
                f.write("# Migrated from db.yml\n\n")
                yaml.dump(infra, f, default_flow_style=False, sort_keys=False)
        except (IOError, PermissionError) as e:
            logger.error(f"Failed to write {traefik_path}: {e}")
            return 1

        logger.info("   ✓ projects/traefik.yml")

        # 2. Migrate projects
        logger.info("")
        logger.info("2. Migrating projects...")

        for project in db.get('projects', []):
            try:
                name = validate_project_name(project.get('name', ''))
            except ValueError as e:
                logger.error(f"   ✗ {e}")
                return 1

            logger.info(f"   {name}...")

            # Create project directory
            project_dir = projects_dir / name
            project_dir.mkdir(exist_ok=True)

            # Copy existing docker-compose.yml from upstream/
            upstream_compose = upstream_dir / name / 'docker-compose.yml'
            if not upstream_compose.exists():
                logger.error(f"     ✗ upstream/{name}/docker-compose.yml not found")
                logger.error(f"       Run 'bin/write-artifacts.py' first to generate V1 artifacts")
                return 1

            try:
                # Read the upstream docker-compose.yml
                with open(upstream_compose, encoding='utf-8') as f:
                    compose_content = f.read()

                # Write to projects/
                with open(project_dir / 'docker-compose.yml', 'w', encoding='utf-8') as f:
                    f.write(compose_content)

                logger.info(f"     ✓ {name}/docker-compose.yml (copied from upstream/)")
            except (IOError, PermissionError) as e:
                logger.error(f"     ✗ Failed to copy docker-compose.yml: {e}")
                return 1

            # Generate traefik.yml from db.yml routing config
            try:
                traefik = migrate_project_traefik_config(project)
            except (ValueError, KeyError) as e:
                logger.error(f"     ✗ Failed to generate traefik config: {e}")
                return 1

            # Write traefik.yml
            try:
                with open(project_dir / 'traefik.yml', 'w', encoding='utf-8') as f:
                    yaml.dump(traefik, f, default_flow_style=False, sort_keys=False)
            except (IOError, PermissionError) as e:
                logger.error(f"     ✗ Failed to write traefik.yml: {e}")
                return 1

            logger.info(f"     ✓ {name}/traefik.yml")

        logger.info("")
        logger.info("=" * 50)
        logger.info("✓ Migration complete!")
        logger.info("")
        logger.info("Files created:")
        logger.info("  - db.yml.v1-backup (old format - CONTAINS PLAINTEXT SECRETS)")
        logger.info("  - projects/traefik.yml (infrastructure)")
        logger.info("  - projects/*/docker-compose.yml (copied from upstream/)")
        logger.info("  - projects/*/traefik.yml (routing)")
        logger.info("")
        logger.info("Next steps:")
        logger.info("  1. Review projects/ structure")
        logger.info("  2. cd projects/ && git add . && git commit && git push")
        logger.info("  3. Keep db.yml.v1-backup secure (for rollback)")
        logger.info("  4. Remove old db.yml when ready: rm db.yml")

        return 0

    except Exception as e:
        logger.error(f"Unexpected error during migration: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    setup_logging()
    sys.exit(main())
