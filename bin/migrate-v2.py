#!/usr/bin/env python3
"""Migrate current db.yml to V2 architecture (projects/ structure)

This script is idempotent - it can be run multiple times and will only
create files that don't exist yet. Use --force to overwrite existing files.
"""

import argparse
import logging
import sys
from pathlib import Path

import yaml

from lib.data import get_db
from lib.logging_config import setup_logging

logger = logging.getLogger(__name__)


def replace_secrets_with_vars(data):
    """Recursively replace secret values with ${VAR} references"""
    # Load secrets map (value -> key)
    secrets = {}
    secrets_file = Path('secrets/global.txt')
    if secrets_file.exists():
        with open(secrets_file, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    secrets[value.strip()] = key.strip()

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


def migrate_infrastructure(db: dict) -> dict:
    """Extract infrastructure config from db.yml → projects/traefik.yml"""

    # Extract infrastructure sections
    infra = {}

    # Copy relevant sections
    for key in ['domain_suffix', 'letsencrypt', 'trusted_ips', 'traefik',
                'middleware', 'plugins', 'versions']:
        if key in db:
            infra[key] = db[key]

    # Replace secrets with ${VAR} references
    infra = replace_secrets_with_vars(infra)

    return infra


def migrate_project(project: dict) -> tuple[dict, dict]:
    """
    Convert project from db.yml to docker-compose.yml + traefik.yml

    Returns: (docker_compose, traefik_config)
    """
    name = project['name']

    # Build docker-compose.yml
    compose = {
        'services': {},
        'networks': {
            'traefik': {'external': True}
        }
    }

    # Project-level env
    project_env = project.get('env', {})

    for service in project.get('services', []):
        service_name = service['host']
        compose_service = {}

        # Basic fields
        if 'image' in service:
            compose_service['image'] = service['image']
        if 'command' in service:
            compose_service['command'] = service['command']
        if 'depends_on' in service:
            compose_service['depends_on'] = service['depends_on']

        # Environment
        env = {}
        env.update(project_env)
        env.update(service.get('env', {}))
        if env:
            compose_service['environment'] = env

        # Volumes
        if 'volumes' in service:
            compose_service['volumes'] = service['volumes']

        # Networks
        compose_service['networks'] = ['traefik']

        # Additional properties
        if 'additional_properties' in service:
            compose_service.update(service['additional_properties'])

        compose['services'][service_name] = compose_service

    # Build traefik.yml
    traefik = {
        'enabled': project.get('enabled', True),
        'ingress': []
    }

    for service in project.get('services', []):
        for ingress in service.get('ingress', []):
            if not ingress:
                continue

            traefik_ingress = {'service': service['host']}

            for key in ['domain', 'port', 'router', 'path_prefix', 'hostport', 'passthrough']:
                if key in ingress:
                    traefik_ingress[key] = ingress[key]

            if 'tls' in ingress and 'sans' in ingress['tls']:
                traefik_ingress['tls_sans'] = ingress['tls']['sans']

            traefik['ingress'].append(traefik_ingress)

    return compose, traefik


def write_file_if_needed(path: Path, content: str, force: bool = False) -> str:
    """
    Write file only if it doesn't exist or force=True.

    Returns: "created", "skipped", or "overwritten"
    """
    if path.exists() and not force:
        return "skipped"

    # Create parent directory if needed
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

    return "overwritten" if path.exists() else "created"


def main():
    parser = argparse.ArgumentParser(
        description='Migrate db.yml to V2 architecture (projects/ structure)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing files (default: skip existing files)'
    )
    args = parser.parse_args()

    setup_logging()

    # Validate prerequisites
    db_path = Path('db.yml')
    if not db_path.exists():
        logger.error("db.yml not found in current directory")
        logger.error("Please run this script from the project root")
        return 1

    projects_dir = Path('projects')
    if not projects_dir.exists():
        logger.error("projects/ directory not found")
        logger.error("Please initialize the projects submodule first")
        return 1

    secrets_file = Path('secrets/global.txt')
    if not secrets_file.exists():
        logger.warning("secrets/global.txt not found - secret replacement will be skipped")

    # Load db.yml using existing utility
    logger.info("Loading db.yml...")
    try:
        db = get_db()
    except FileNotFoundError:
        logger.error("db.yml not found - please run from project root")
        return 1
    except yaml.YAMLError as e:
        logger.error(f"Invalid YAML in db.yml: {e}")
        return 1

    if args.force:
        logger.warning("--force flag provided - will overwrite existing files")

    logger.info("Migrating to V2 architecture...")
    logger.info("")

    # Track statistics
    stats = {'created': 0, 'skipped': 0, 'overwritten': 0}

    # 1. Backup db.yml (only if doesn't exist or force)
    backup_path = Path('db.yml.v1-backup')
    backup_content = yaml.dump(db, default_flow_style=False, sort_keys=False)
    result = write_file_if_needed(backup_path, backup_content, args.force)
    stats[result] += 1
    logger.info(f"Backup: db.yml.v1-backup [{result}]")

    # 2. Migrate infrastructure config
    logger.info("")
    logger.info("Extracting infrastructure config...")
    infra = migrate_infrastructure(db)

    infra_path = projects_dir / 'traefik.yml'
    infra_content = "# Infrastructure configuration\n"
    infra_content += "# Migrated from db.yml\n\n"
    infra_content += yaml.dump(infra, default_flow_style=False, sort_keys=False)

    result = write_file_if_needed(infra_path, infra_content, args.force)
    stats[result] += 1
    logger.info(f"  projects/traefik.yml [{result}]")

    # 3. Migrate projects
    logger.info("")
    logger.info("Migrating projects...")

    for project in db.get('projects', []):
        name = project['name']
        logger.info(f"  {name}...")

        # Generate configs
        compose, traefik = migrate_project(project)

        # Create project directory
        project_dir = projects_dir / name
        project_dir.mkdir(exist_ok=True)

        # Write docker-compose.yml
        compose_path = project_dir / 'docker-compose.yml'
        compose_content = yaml.dump(compose, default_flow_style=False, sort_keys=False)
        result = write_file_if_needed(compose_path, compose_content, args.force)
        stats[result] += 1
        logger.info(f"    {name}/docker-compose.yml [{result}]")

        # Write traefik.yml
        traefik_path = project_dir / 'traefik.yml'
        traefik_content = yaml.dump(traefik, default_flow_style=False, sort_keys=False)
        result = write_file_if_needed(traefik_path, traefik_content, args.force)
        stats[result] += 1
        logger.info(f"    {name}/traefik.yml [{result}]")

    # Summary
    logger.info("")
    logger.info("=" * 50)
    logger.info("Migration complete!")
    logger.info("")
    logger.info(f"Statistics:")
    logger.info(f"  Created: {stats['created']}")
    logger.info(f"  Skipped: {stats['skipped']}")
    logger.info(f"  Overwritten: {stats['overwritten']}")
    logger.info("")

    if stats['skipped'] > 0 and not args.force:
        logger.info("Some files were skipped because they already exist.")
        logger.info("Run with --force to overwrite existing files.")
        logger.info("")

    logger.info("Files structure:")
    logger.info("  - db.yml.v1-backup (old format)")
    logger.info("  - projects/traefik.yml (infrastructure)")
    logger.info("  - projects/*/docker-compose.yml (services)")
    logger.info("  - projects/*/traefik.yml (routing)")
    logger.info("")
    logger.info("Next steps:")
    logger.info("  1. Review projects/ structure")
    logger.info("  2. cd projects/ && git add . && git commit && git push")
    logger.info("  3. Remove old db.yml: rm db.yml")

    return 0


if __name__ == '__main__':
    sys.exit(main())
