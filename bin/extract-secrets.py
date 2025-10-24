#!/usr/bin/env python3
"""Extract secrets from db.yml to secrets/ files"""

import re
import yaml
from pathlib import Path


def is_secret(key: str, value: str) -> bool:
    """Detect if a value is likely a secret"""
    secret_keywords = [
        'password', 'secret', 'key', 'token', 'api', 'auth',
        'smtp', 'db_pass', 'redis_pass', 'api_key', 'htpasswd'
    ]

    key_lower = key.lower()

    # Check key name
    if any(kw in key_lower for kw in secret_keywords):
        return True

    # Check value patterns
    if isinstance(value, str):
        # Long random strings
        if len(value) > 20 and re.match(r'^[A-Za-z0-9+/=_-]+$', value):
            return True
        # JWT/API key patterns
        if value.startswith(('sk-', 'pk-', 'Bearer ', '$apr1$', '$2')):
            return True

    return False


def extract_env_from_dict(data: dict, prefix: str = "") -> dict:
    """Recursively extract all env vars"""
    env_vars = {}

    for key, value in data.items():
        var_name = f"{prefix}_{key}".upper() if prefix else key.upper()

        if isinstance(value, dict):
            env_vars.update(extract_env_from_dict(value, var_name))
        elif isinstance(value, str):
            env_vars[var_name] = value

    return env_vars


def main():
    # Load current db.yml
    with open('db.yml') as f:
        db = yaml.safe_load(f)

    # Create db.yml backup
    with open('db.yml.backup', 'w') as f:
        yaml.dump(db, f)

    # Extract all env vars
    all_vars = {}

    # From plugins
    if 'plugins' in db:
        for plugin, config in db['plugins'].items():
            if isinstance(config, dict):
                vars = extract_env_from_dict(config, f'{plugin}')
                all_vars.update(vars)

    # From projects
    if 'projects' in db:
        for project in db['projects']:
            name = project.get('name', '')
            if 'env' in project:
                vars = extract_env_from_dict(project['env'], name)
                all_vars.update(vars)

    # Separate secrets from non-secrets
    secrets = {}
    config_vars = {}

    for key, value in all_vars.items():
        if is_secret(key, value):
            secrets[key] = value
        else:
            config_vars[key] = value

    # Write secrets to secrets/global.txt
    secrets_dir = Path('secrets')
    with open(secrets_dir / 'global.txt', 'w') as f:
        f.write("# Shared secrets extracted from db.yml\n")
        f.write("# Review and deduplicate before encrypting\n\n")
        for key, value in sorted(secrets.items()):
            f.write(f"{key}={value}\n")

    print(f"✓ Extracted {len(secrets)} secrets to secrets/global.txt")
    print(f"  Review for duplicates (SMTP, OpenAI keys appear multiple times)")
    print(f"\nNext steps:")
    print(f"  1. cd secrets/")
    print(f"  2. Edit global.txt to deduplicate")
    print(f"  3. sops -e global.txt > global.enc.txt")
    print(f"  4. git add global.enc.txt && git commit && git push")


if __name__ == '__main__':
    main()
