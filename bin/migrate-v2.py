#!/usr/bin/env python3
"""Migrate current db.yml to V2 architecture"""

import os
import sys
import yaml
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

def migrate_infrastructure(db: dict) -> dict:
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

def replace_secrets_with_vars(data):
    """Recursively replace secret values with ${VAR} references"""
    # Load secrets map
    secrets = {}
    secrets_file = Path('secrets/global.txt')
    if secrets_file.exists():
        with open(secrets_file) as f:
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

    # Replace secrets with ${VAR} references
    compose = replace_secrets_with_vars(compose)
    traefik = replace_secrets_with_vars(traefik)

    return compose, traefik

def main():
    # Load db.yml
    with open('db.yml') as f:
        db = yaml.safe_load(f)

    # Backup
    with open('db.yml.v1-backup', 'w') as f:
        yaml.dump(db, f)

    print("Migrating to V2 architecture...")
    print()

    # Ensure projects/ directory exists
    projects_dir = Path('projects')
    projects_dir.mkdir(exist_ok=True)

    # 1. Migrate infrastructure config
    print("1. Extracting infrastructure config...")
    infra = migrate_infrastructure(db)

    with open('projects/traefik.yml', 'w') as f:
        f.write("# Infrastructure configuration\n")
        f.write("# Migrated from db.yml\n\n")
        yaml.dump(infra, f, default_flow_style=False, sort_keys=False)

    print("   ✓ projects/traefik.yml")

    # 2. Migrate projects
    print("\n2. Migrating projects...")

    for project in db.get('projects', []):
        name = project['name']
        print(f"   {name}...")

        # Create project directory
        project_dir = Path(f'projects/{name}')
        project_dir.mkdir(exist_ok=True)

        # Generate configs
        compose, traefik = migrate_project(project)

        # Write docker-compose.yml
        with open(project_dir / 'docker-compose.yml', 'w') as f:
            yaml.dump(compose, f, default_flow_style=False, sort_keys=False)

        # Write traefik.yml
        with open(project_dir / 'traefik.yml', 'w') as f:
            yaml.dump(traefik, f, default_flow_style=False, sort_keys=False)

        print(f"     ✓ {name}/docker-compose.yml")
        print(f"     ✓ {name}/traefik.yml")

    print("\n" + "=" * 50)
    print("✓ Migration complete!")
    print()
    print("Files created:")
    print("  - db.yml.v1-backup (old format)")
    print("  - projects/traefik.yml (infrastructure)")
    print("  - projects/*/docker-compose.yml (services)")
    print("  - projects/*/traefik.yml (routing)")
    print()
    print("Next steps:")
    print("  1. Review projects/ structure")
    print("  2. cd projects/ && git add . && git commit && git push")
    print("  3. Remove old db.yml: rm db.yml")

if __name__ == '__main__':
    main()
