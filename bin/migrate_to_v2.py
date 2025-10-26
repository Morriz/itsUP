#!/usr/bin/env python3
"""Migrate V1 upstream/ + db.yml to V2 projects/ + secrets/

Correct migration direction:
  upstream/{name}/docker-compose.yml → projects/{name}/docker-compose.yml (strip labels)
  upstream/{name}/docker-compose.yml → projects/{name}/ingress.yml (extract labels)
  upstream/{name}/.env → secrets/{name}.txt
  db.yml → secrets/itsup.txt (infrastructure secrets)
  db.yml → projects/traefik.yml (infrastructure config)

This script is idempotent - run with --force to overwrite existing files.
"""

import argparse
import logging
import re
import sys
from pathlib import Path

import yaml
from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.logging_config import setup_logging

logger = logging.getLogger(__name__)


def extract_literal_secrets(compose: dict, project_name: str) -> dict:
    """Extract literal environment variable values (not ${VAR} references)

    Returns: dict of {VAR_NAME: literal_value}
    """
    secrets = {}

    for service_name, service_config in compose.get("services", {}).items():
        env = service_config.get("environment", {})

        # Handle both dict and list formats
        if isinstance(env, dict):
            env_dict = env
        elif isinstance(env, list):
            env_dict = {}
            for item in env:
                if "=" in item:
                    key, value = item.split("=", 1)
                    env_dict[key] = value
        else:
            continue

        # Extract literal values (not ${VAR} or $VAR)
        for key, value in env_dict.items():
            if isinstance(value, str):
                # Skip if it's a variable reference
                if value.startswith("${") and value.endswith("}"):
                    continue
                if value.startswith("$"):
                    continue
                # It's a literal value - extract it (use original key name)
                secrets[key] = value

    return secrets


def replace_literals_with_vars(compose: dict, secrets: dict) -> dict:
    """Replace literal env values with ${VAR} references

    Args:
        compose: Docker compose dict
        secrets: Dict of {VAR_NAME: literal_value} to replace

    Returns: Updated compose with ${VAR} references
    """
    # Create reverse lookup: literal_value -> VAR_NAME
    value_to_var = {v: k for k, v in secrets.items()}

    clean_compose = compose.copy()

    for service_name, service_config in clean_compose.get("services", {}).items():
        if "environment" not in service_config:
            continue

        env = service_config["environment"]

        # Handle dict format
        if isinstance(env, dict):
            for key, value in env.items():
                if isinstance(value, str) and value in value_to_var:
                    env[key] = f"${{{value_to_var[value]}}}"

        # Handle list format
        elif isinstance(env, list):
            new_env = []
            for item in env:
                if "=" in item:
                    key, value = item.split("=", 1)
                    if value in value_to_var:
                        new_env.append(f"{key}=${{{value_to_var[value]}}}")
                    else:
                        new_env.append(item)
                else:
                    new_env.append(item)
            service_config["environment"] = new_env

    return clean_compose


def strip_traefik_labels(compose: dict) -> dict:
    """Remove all Traefik labels from docker-compose services"""
    clean_compose = compose.copy()

    for service_name, service_config in clean_compose.get("services", {}).items():
        if "labels" in service_config:
            # Remove all traefik.* labels
            labels = service_config["labels"]
            if isinstance(labels, list):
                non_traefik = [l for l in labels if not l.startswith("traefik.")]
                if non_traefik:
                    service_config["labels"] = non_traefik
                else:
                    del service_config["labels"]
            elif isinstance(labels, dict):
                non_traefik = {k: v for k, v in labels.items() if not k.startswith("traefik.")}
                if non_traefik:
                    service_config["labels"] = non_traefik
                else:
                    del service_config["labels"]

        # Remove proxynet network (will be added by artifact generation)
        if "networks" in service_config:
            networks = service_config["networks"]
            if isinstance(networks, list):
                networks = [n for n in networks if n != "proxynet"]
                if networks:
                    service_config["networks"] = networks
                else:
                    del service_config["networks"]
            elif isinstance(networks, dict):
                networks = {k: v for k, v in networks.items() if k != "proxynet"}
                if networks:
                    service_config["networks"] = networks
                else:
                    del service_config["networks"]

    # Remove proxynet from networks section
    if "networks" in clean_compose:
        networks = clean_compose["networks"]
        if "proxynet" in networks:
            del networks["proxynet"]
        if not networks:
            del clean_compose["networks"]

    return clean_compose


def extract_ingress_from_labels(compose: dict, project_name: str) -> dict:
    """Extract ingress.yml config from Traefik labels"""
    ingress_config = {"enabled": False, "ingress": []}

    for service_name, service_config in compose.get("services", {}).items():
        labels = service_config.get("labels", [])

        # Convert dict to list
        if isinstance(labels, dict):
            labels = [f"{k}={v}" for k, v in labels.items()]

        # Parse labels into dict
        label_dict = {}
        for label in labels:
            if "=" in label:
                key, value = label.split("=", 1)
                label_dict[key] = value

        # Check if Traefik is enabled
        if label_dict.get("traefik.enable") != "true":
            continue

        ingress_config["enabled"] = True

        # Detect router type (http, tcp, udp)
        router_type = None
        router_name = None

        for key in label_dict.keys():
            if ".http.routers." in key:
                router_type = "http"
                router_name = key.split(".http.routers.")[1].split(".")[0]
                break
            elif ".tcp.routers." in key:
                router_type = "tcp"
                router_name = key.split(".tcp.routers.")[1].split(".")[0]
                break
            elif ".udp.routers." in key:
                router_type = "udp"
                router_name = key.split(".udp.routers.")[1].split(".")[0]
                break

        if not router_type:
            logger.warning(f"Could not detect router type for {service_name}")
            continue

        # Build ingress entry
        ingress_entry = {"service": service_name, "router": router_type}

        # Extract domain from rule
        rule_key = f"traefik.{router_type}.routers.{router_name}.rule"
        if rule_key in label_dict:
            rule = label_dict[rule_key]
            # Extract domain from Host(`domain`) or HostSNI(`domain`)
            match = re.search(r"Host(?:SNI)?\(`([^`]+)`\)", rule)
            if match:
                ingress_entry["domain"] = match.group(1)

            # Extract path prefix
            if "PathPrefix(" in rule:
                match = re.search(r"PathPrefix\(`([^`]+)`\)", rule)
                if match:
                    ingress_entry["path_prefix"] = match.group(1)

        # Extract port
        port_key = f"traefik.{router_type}.services.{router_name}.loadbalancer.server.port"
        if port_key in label_dict:
            ingress_entry["port"] = int(label_dict[port_key])

        # Extract entrypoint for hostport
        entrypoint_key = f"traefik.{router_type}.routers.{router_name}.entrypoints"
        if entrypoint_key in label_dict:
            entrypoint = label_dict[entrypoint_key]
            # Extract port from tcp-8080 or udp-8080
            if entrypoint.startswith(f"{router_type}-"):
                port_str = entrypoint.split("-", 1)[1]
                if port_str.isdigit():
                    ingress_entry["hostport"] = int(port_str)

        # Check for TLS passthrough
        passthrough_key = f"traefik.{router_type}.routers.{router_name}.tls.passthrough"
        if label_dict.get(passthrough_key) == "true":
            ingress_entry["passthrough"] = True

        ingress_config["ingress"].append(ingress_entry)

    return ingress_config


def extract_infrastructure_secrets(db: dict) -> dict:
    """Extract infrastructure secrets from db.yml to secrets/itsup.txt format"""
    secrets = {}

    # Let's Encrypt
    if "letsencrypt" in db:
        le = db["letsencrypt"]
        if "email" in le:
            secrets["LETSENCRYPT_EMAIL"] = le["email"]

    # Traefik
    if "traefik" in db:
        tf = db["traefik"]
        if "domain" in tf:
            secrets["TRAEFIK_DOMAIN"] = tf["domain"]
        if "admin" in tf:
            secrets["TRAEFIK_ADMIN"] = tf["admin"]

    # CrowdSec
    if "plugins" in db and "crowdsec" in db["plugins"]:
        cs = db["plugins"]["crowdsec"]
        if "apikey" in cs:
            secrets["CROWDSEC_API_KEY"] = cs["apikey"]
            secrets["CROWDSEC_APIKEY"] = cs["apikey"]
        if "options" in cs:
            opts = cs["options"]
            if "crowdsecCapiMachineId" in opts:
                secrets["CROWDSEC_CAPI_MACHINE_ID"] = opts["crowdsecCapiMachineId"]
            if "crowdsecCapiPassword" in opts:
                secrets["CROWDSEC_CAPI_PASSWORD"] = opts["crowdsecCapiPassword"]

    return secrets


def extract_infrastructure_config(db: dict) -> dict:
    """Extract infrastructure config from db.yml to projects/traefik.yml"""
    config = {}

    # CrowdSec plugin config (if enabled)
    if "plugins" in db and "crowdsec" in db["plugins"]:
        cs = db["plugins"]["crowdsec"]
        if cs.get("enabled"):
            # Build Traefik plugin structure with ${VAR} references
            config["experimental"] = {
                "plugins": {
                    "bouncer": {
                        "moduleName": "github.com/maxlerebourg/crowdsec-bouncer-traefik-plugin",
                        "version": cs.get("version", "v1.2.0"),
                    }
                }
            }

            config["plugins"] = {
                "crowdsec": {"enabled": True, "apikey": "${CROWDSEC_APIKEY}", "collections": cs.get("collections", [])}
            }

            if "options" in cs:
                opts = cs["options"]
                config["plugins"]["crowdsec"]["options"] = {
                    "crowdsecCapiMachineId": "${CROWDSEC_CAPI_MACHINE_ID}",
                    "crowdsecCapiPassword": "${CROWDSEC_CAPI_PASSWORD}",
                    "crowdsecCapiScenarios": opts.get("crowdsecCapiScenarios", []),
                    "defaultDecisionSeconds": opts.get("defaultDecisionSeconds", 600),
                    "httpTimeoutSeconds": opts.get("httpTimeoutSeconds", 10),
                    "logLevel": opts.get("logLevel", "WARN"),
                    "updateIntervalSeconds": opts.get("updateIntervalSeconds", 60),
                }

    # Let's Encrypt
    config["certificatesResolvers"] = {"letsencrypt": {"acme": {"email": "${LETSENCRYPT_EMAIL}"}}}

    # Middleware (if exists)
    if "middleware" in db:
        config["middlewares"] = db["middleware"]

    return config


def write_file(path: Path, content: str, force: bool = False) -> str:
    """Write file if needed. Returns: 'created', 'skipped', or 'overwritten'"""
    if path.exists() and not force:
        return "skipped"

    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return "overwritten" if path.exists() else "created"


def main():
    parser = argparse.ArgumentParser(description="Migrate V1 (upstream/ + db.yml) to V2 (projects/ + secrets/)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without doing it")
    args = parser.parse_args()

    setup_logging()

    # Validate prerequisites
    upstream_dir = Path("upstream")
    if not upstream_dir.exists():
        logger.error("upstream/ directory not found")
        return 1

    db_path = Path("db.yml")
    if not db_path.exists():
        logger.error("db.yml not found")
        return 1

    projects_dir = Path("projects")
    if not projects_dir.exists():
        logger.error("projects/ directory not found - run 'itsup init' first")
        return 1

    secrets_dir = Path("secrets")
    if not secrets_dir.exists():
        logger.error("secrets/ directory not found - run 'itsup init' first")
        return 1

    if args.dry_run:
        logger.info("DRY RUN MODE - no files will be modified")
        logger.info("")

    if args.force:
        logger.warning("--force flag enabled - will overwrite existing files")
        logger.info("")

    # Load db.yml
    logger.info("Loading db.yml...")
    with open(db_path, encoding="utf-8") as f:
        db = yaml.safe_load(f)

    stats = {"created": 0, "skipped": 0, "overwritten": 0}

    # 1. Backup db.yml
    logger.info("Creating backup...")
    backup_path = Path("db.yml.v1-backup")
    backup_content = yaml.dump(db, default_flow_style=False, sort_keys=False)
    if not args.dry_run:
        result = write_file(backup_path, backup_content, args.force)
        stats[result] += 1
        logger.info(f"  db.yml.v1-backup [{result}]")
    else:
        logger.info("  Would create: db.yml.v1-backup")

    # 2. Extract infrastructure secrets
    logger.info("")
    logger.info("Extracting infrastructure secrets...")
    infra_secrets = extract_infrastructure_secrets(db)

    secrets_path = secrets_dir / "itsup.txt"
    secrets_lines = ["# Infrastructure secrets (migrated from db.yml)\n"]
    for key, value in infra_secrets.items():
        secrets_lines.append(f"{key}={value}\n")

    if not args.dry_run:
        # Append to existing file or create new
        if secrets_path.exists() and not args.force:
            logger.info("  secrets/itsup.txt [skipped - already exists]")
            logger.info("  Add these manually:")
            for line in secrets_lines[1:]:
                logger.info(f"    {line.strip()}")
        else:
            result = write_file(secrets_path, "".join(secrets_lines), args.force)
            stats[result] += 1
            logger.info(f"  secrets/itsup.txt [{result}]")
    else:
        logger.info("  Would write to: secrets/itsup.txt")
        for line in secrets_lines[1:]:
            logger.info(f"    {line.strip()}")

    # 3. Extract infrastructure config
    logger.info("")
    logger.info("Extracting infrastructure config...")
    infra_config = extract_infrastructure_config(db)

    traefik_path = projects_dir / "traefik.yml"
    traefik_content = "# Infrastructure configuration (migrated from db.yml)\n\n"
    traefik_content += yaml.dump(infra_config, default_flow_style=False, sort_keys=False)

    if not args.dry_run:
        result = write_file(traefik_path, traefik_content, args.force)
        stats[result] += 1
        logger.info(f"  projects/traefik.yml [{result}]")
    else:
        logger.info("  Would write to: projects/traefik.yml")

    # 4. Migrate each upstream project
    logger.info("")
    logger.info("Migrating upstream projects...")

    for project_dir in sorted(upstream_dir.iterdir()):
        if not project_dir.is_dir():
            continue

        project_name = project_dir.name
        logger.info(f"  {project_name}...")

        # Read upstream docker-compose.yml
        upstream_compose_path = project_dir / "docker-compose.yml"
        if not upstream_compose_path.exists():
            logger.warning("    No docker-compose.yml found, skipping")
            continue

        with open(upstream_compose_path, encoding="utf-8") as f:
            upstream_compose = yaml.safe_load(f)

        # Extract ingress config from labels FIRST (before stripping!)
        ingress_config = extract_ingress_from_labels(upstream_compose, project_name)

        # Extract literal secrets from environment variables
        project_secrets = extract_literal_secrets(upstream_compose, project_name)

        # Replace literal values with ${VAR} references
        clean_compose = replace_literals_with_vars(upstream_compose, project_secrets)

        # Then strip Traefik labels
        clean_compose = strip_traefik_labels(clean_compose)

        # Create project directory
        project_path = projects_dir / project_name

        # Write docker-compose.yml
        compose_path = project_path / "docker-compose.yml"
        compose_content = yaml.dump(clean_compose, default_flow_style=False, sort_keys=False)

        if not args.dry_run:
            result = write_file(compose_path, compose_content, args.force)
            stats[result] += 1
            logger.info(f"    docker-compose.yml [{result}]")
        else:
            logger.info("    Would write: docker-compose.yml")

        # Write ingress.yml
        ingress_path = project_path / "ingress.yml"
        ingress_content = yaml.dump(ingress_config, default_flow_style=False, sort_keys=False)

        if not args.dry_run:
            result = write_file(ingress_path, ingress_content, args.force)
            stats[result] += 1
            logger.info(f"    ingress.yml [{result}]")
        else:
            logger.info("    Would write: ingress.yml")

        # Write project secrets (from extracted literals + .env file if exists)
        combined_secrets = {}

        # 1. Add extracted literal secrets
        combined_secrets.update(project_secrets)

        # 2. Add secrets from .env file if exists
        env_path = project_dir / ".env"
        if env_path.exists():
            env_values = dotenv_values(env_path)
            combined_secrets.update(env_values)

        # Write secrets file if we have any
        if combined_secrets:
            project_secrets_path = secrets_dir / f"{project_name}.txt"

            secrets_content = f"# Project secrets for {project_name}\n"
            if project_secrets:
                secrets_content += "# Extracted from environment variables\n"
            if env_path.exists():
                secrets_content += f"# Migrated from upstream/{project_name}/.env\n"
            secrets_content += "\n"

            for key, value in combined_secrets.items():
                secrets_content += f"{key}={value}\n"

            if not args.dry_run:
                result = write_file(project_secrets_path, secrets_content, args.force)
                stats[result] += 1
                logger.info(f"    secrets/{project_name}.txt [{result}] ({len(combined_secrets)} secrets)")
            else:
                logger.info(f"    Would write: secrets/{project_name}.txt ({len(combined_secrets)} secrets)")

    # Summary
    logger.info("")
    logger.info("=" * 60)
    if args.dry_run:
        logger.info("DRY RUN COMPLETE - no files were modified")
    else:
        logger.info("Migration complete!")
        logger.info("")
        logger.info("Statistics:")
        logger.info(f"  Created: {stats['created']}")
        logger.info(f"  Skipped: {stats['skipped']}")
        logger.info(f"  Overwritten: {stats['overwritten']}")

    logger.info("")
    logger.info("Next steps:")
    logger.info("  1. Review migrated files in projects/ and secrets/")
    logger.info("  2. Test artifact generation: itsup apply")
    logger.info("  3. Commit changes: itsup commit 'Migrated to V2'")
    logger.info("  4. Delete old files: rm -rf upstream/ db.yml")

    return 0


if __name__ == "__main__":
    sys.exit(main())
