"""Data loading from projects/ and secrets/"""

import hashlib
import ipaddress
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from instrukt_ai_logging import get_logger

try:
    import netifaces
except ImportError:
    # Optional C-extension; only needed for router-IP auto-detection. Keeping the
    # module importable without it lets every interpreter (CI, dev) load lib.data.
    netifaces = None

from lib.models import BackupConfig, TraefikConfig
from lib.paths import root
from lib.sops import load_encrypted_env, load_env_file

logger = get_logger(f"itsup.{__name__}")

# proxynet subnet (created by the DNS stack in dns/docker-compose.yml).
# Static ingress IPs must lie within it and avoid the gateway/honeypot.
PROXYNET_SUBNET = "172.20.0.0/16"
PROXYNET_RESERVED_IPS = {"172.20.0.1", "172.20.0.253"}

COMPOSE_SCHEMA_CHECK_TIMEOUT = 30
COMPOSE_SCHEMA_FAILURE_PREFIX = "docker compose schema validation failed"

# === V2 API Functions (for projects/ structure) ===


def load_secrets(project_name: str | None = None) -> dict[str, str]:
    """Load secrets from secrets/ (auto-detects encrypted .enc.txt or plaintext .txt)

    Auto-detection priority for each file:
    1. Try encrypted: secrets/{name}.enc.txt (decrypted with SOPS)
    2. Fall back to plaintext: secrets/{name}.txt (development only)

    Secret organization:
    - secrets/itsup.{enc.txt|txt} = itsUP infrastructure secrets (DNS, proxy, API)
    - secrets/{project}.{enc.txt|txt} = Project-specific secrets (one file per project)

    Args:
        project_name: Optional project name to load project-specific secrets.
                     If None, only loads itsup.{enc.txt|txt} for infrastructure.

    Returns:
        Dictionary of secret key-value pairs
    """
    secrets: dict[str, str] = {}
    secrets_dir = root() / "secrets"

    if not secrets_dir.exists():
        logger.warning("secrets/ directory not found")
        return secrets

    def _load_secret_file(name: str) -> dict[str, str]:
        """Load secret file with auto-detection (encrypted first, then plaintext)"""
        encrypted_file = secrets_dir / f"{name}.enc.txt"
        plaintext_file = secrets_dir / f"{name}.txt"

        # Try encrypted first (production)
        if encrypted_file.exists():
            env_vars = load_encrypted_env(encrypted_file)
            if env_vars:
                logger.debug("Loaded %d secrets from %s.enc.txt (SOPS encrypted)", len(env_vars), name)
                return env_vars
            logger.warning("Failed to decrypt %s.enc.txt, trying plaintext...", name)

        # Fall back to plaintext (development)
        if plaintext_file.exists():
            env_vars = load_env_file(plaintext_file)
            logger.debug("Loaded %d secrets from %s.txt (plaintext - development only)", len(env_vars), name)
            if os.environ.get("PYTHON_ENV") == "production":
                logger.warning("Using plaintext secrets in production: %s.txt", name)
            return env_vars

        return {}

    # Load secrets based on context
    if project_name:
        # Project deployment: load ONLY project-specific secrets
        secrets.update(_load_secret_file(project_name))
    else:
        # Infrastructure: load ONLY itsup secrets
        secrets.update(_load_secret_file("itsup"))

    context = f" for {project_name}" if project_name else " for itsUP infrastructure"
    logger.info("Loaded %d secrets%s", len(secrets), context)
    return secrets


def get_env_with_secrets(project_name: str | None = None) -> dict[str, str]:
    """Build environment dict with secrets loaded

    This is the standard pattern for running docker compose commands that need secrets.
    Combines current environment with loaded secrets.

    Args:
        project_name: Optional project name to load project-specific secrets

    Returns:
        Dictionary combining os.environ with secrets (secrets override env)

    Example:
        env = get_env_with_secrets()
        subprocess.run(cmd, env=env, check=True)
    """
    secrets = load_secrets(project_name)
    return {**os.environ, **secrets}


def load_project(project_name: str) -> tuple[dict[str, Any], TraefikConfig]:
    """
    Load project from projects/{name}/

    Supports two types of projects:
    1. Container projects: have docker-compose.yml + optional ingress.yml
    2. External host passthroughs: have only ingress.yml (no containers)

    Args:
        project_name: Name of the project to load

    Returns: (docker_compose_dict, ingress_config)
        For external hosts, docker_compose_dict will be empty {}
        Secrets are left as ${VAR} placeholders for runtime expansion by Docker Compose
    """
    project_dir = root() / "projects" / project_name

    if not project_dir.exists():
        raise FileNotFoundError(f"Project not found: {project_name}")

    # Load docker-compose.yml (optional for external host passthroughs)
    compose_file = project_dir / "docker-compose.yml"
    if compose_file.exists():
        with open(compose_file, encoding="utf-8") as f:
            compose = yaml.safe_load(f)
    else:
        # No docker-compose.yml - this is an ingress-only external host project
        compose = {}

    # Load itsup-project.yml (or ingress.yml for backward compatibility)
    new_config_file = project_dir / "itsup-project.yml"
    old_config_file = project_dir / "ingress.yml"

    # Initialize with defaults
    traefik = TraefikConfig()

    if new_config_file.exists():
        config_file = new_config_file
    elif old_config_file.exists():
        config_file = old_config_file
        logger.warning(
            "⚠️  %s/ingress.yml is deprecated. " "Rename to itsup-project.yml (support ends in v3.0)",
            project_name,
        )
    else:
        if not compose:
            raise FileNotFoundError(
                f"Project {project_name} has neither docker-compose.yml " f"nor itsup-project.yml/ingress.yml"
            )
        logger.warning("No itsup-project.yml for %s, using defaults", project_name)
        config_file = None

    if config_file:
        with open(config_file, encoding="utf-8") as f:
            traefik_data = yaml.safe_load(f)
            traefik = TraefikConfig(**traefik_data)

    # Secrets are left as ${VAR} for Docker Compose to expand at runtime
    return compose, traefik


def load_project_backup_config(project_name: str) -> BackupConfig | None:
    """Load projects/<name>/backup.yml, the per-project backup registry entry.

    Returns a BackupConfig when the file is present, or None when the project
    declares no backup config. Presence drives both adapter dispatch and the
    derived live-tar exclusion (see project/design/backup-restore).
    """
    backup_file = root() / "projects" / project_name / "backup.yml"
    if not backup_file.exists():
        return None

    with open(backup_file, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return BackupConfig(**data)


def resolve_backup_adapter(project_name: str, adapter: str) -> Path | None:
    """Resolve an adapter name to its script path, project-local first.

    Resolution order (see project/design/backup-restore):
      1. projects/<project>/backup-adapter.sh — the project's own adapter, so a
         new store can be fully self-contained with no change to the framework.
      2. bin/backup-adapters/<adapter>.sh — the shared adapter set.

    Returns the first existing path, or None when neither is present.
    """
    project_local = root() / "projects" / project_name / "backup-adapter.sh"
    if project_local.exists():
        return project_local

    shared = root() / "bin" / "backup-adapters" / f"{adapter}.sh"
    if shared.exists():
        return shared

    return None


def list_projects() -> list[str]:
    """List all available projects (both container and ingress-only)"""
    projects_dir = root() / "projects"
    if not projects_dir.exists():
        return []

    return [
        p.name
        for p in projects_dir.iterdir()
        if p.is_dir()
        and ((p / "docker-compose.yml").exists() or (p / "itsup-project.yml").exists() or (p / "ingress.yml").exists())
        and not p.name.startswith(".")
    ]


def edge_network_name(consumer: str, provider: str, service: str) -> str:
    """Deterministic, Docker-safe name for a per-edge egress network.

    Consumer joins this as external; provider declares and creates it.
    Falls back to a hash-based name when the natural name exceeds 64 chars.
    """
    raw = f"{consumer}--{provider}--{service}"
    if len(raw) <= 64:
        return raw
    return f"egress-{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


def build_reverse_egress_graph() -> dict[str, list[tuple[str, str]]]:
    """Return a mapping from each provider project to its (consumer, service) pairs.

    Scans all projects' egress declarations and inverts the graph so that
    provider projects can enumerate which edge networks they need to create.
    """
    graph: dict[str, list[tuple[str, str]]] = {}
    for proj in list_projects():
        try:
            _, traefik = load_project(proj)
        except Exception:  # pylint: disable=broad-exception-caught
            continue
        for egress_spec in traefik.egress:
            if not egress_spec or ":" not in egress_spec:
                continue
            provider, service = egress_spec.split(":", 1)
            graph.setdefault(provider, []).append((proj, service))
    return graph


def list_projects_topo() -> list[str]:
    """List projects in dependency order based on egress declarations.

    Project P with `egress: [Q:service, ...]` joins a per-edge network created
    by Q, so Q must be deployed first or the `docker compose up` for P fails
    with the edge network declared as external but not found.
    Kahn's algorithm with alphabetical tie-breaking gives a deterministic order.
    A dependency cycle (invalid config) falls back to alphabetical with a
    warning rather than crashing — validate_all surfaces the actual config bug.
    """
    projects = sorted(list_projects())
    deps: dict[str, set[str]] = {p: set() for p in projects}

    for proj in projects:
        try:
            _, traefik = load_project(proj)
        except Exception:  # pylint: disable=broad-exception-caught
            continue  # validate_all surfaces the real error
        for egress_spec in traefik.egress:
            if not egress_spec or ":" not in egress_spec:
                continue
            target = egress_spec.split(":", 1)[0]
            if target in deps and target != proj:
                deps[proj].add(target)

    ordered: list[str] = []
    remaining = set(projects)
    while remaining:
        ready = sorted(p for p in remaining if not deps[p])
        if not ready:
            # Cycle: surface the projects involved and fall back to alphabetical
            logger.warning(
                "Egress dependency cycle detected among %s; falling back to alphabetical order",
                sorted(remaining),
            )
            return projects
        for n in ready:
            ordered.append(n)
            remaining.discard(n)
            for p in remaining:
                deps[p].discard(n)

    return ordered


def _validate_ingress_ips(traefik: TraefikConfig) -> list[str]:
    """Validate static proxynet ipv4_address declarations on a project's ingress rows."""
    errors: list[str] = []
    service_ips: dict[str, str] = {}
    proxynet = ipaddress.ip_network(PROXYNET_SUBNET)

    for ingress in traefik.ingress:
        if ingress is None or not ingress.ipv4_address:
            continue
        ip = ingress.ipv4_address
        # IPv4 format is already validated by Ingress.check_ipv4_address at
        # model construction (inside load_project); ip is guaranteed parseable.
        addr = ipaddress.IPv4Address(ip)
        if addr not in proxynet:
            errors.append(f"ingress.ipv4_address '{ip}' is outside proxynet subnet {PROXYNET_SUBNET}")
        if ip in PROXYNET_RESERVED_IPS:
            errors.append(f"ingress.ipv4_address '{ip}' is reserved (proxynet gateway/honeypot)")
        prev = service_ips.get(ingress.service)
        if prev and prev != ip:
            errors.append(f"service '{ingress.service}' has conflicting ipv4_address values: {prev} and {ip}")
        service_ips[ingress.service] = ip

    return errors


def _validate_egress_targets(traefik: TraefikConfig) -> list[str]:
    """Validate that each egress declaration points at an existing project:service."""
    errors: list[str] = []

    for egress_spec in traefik.egress:
        if not egress_spec:
            continue

        # Parse target service name (format: project:service)
        # Example: "ai-chatbot:redis" -> project="ai-chatbot", service="redis"
        if ":" not in egress_spec:
            errors.append(f"egress '{egress_spec}' must be in format: project:service (e.g., 'ai-chatbot:redis')")
            continue

        target_project, target_service = egress_spec.split(":", 1)

        # Check if target project exists
        if target_project not in list_projects():
            errors.append(f"egress target project '{target_project}' not found (from: {egress_spec})")
            continue

        # Load target project and check if service exists
        try:
            target_compose, _ = load_project(target_project)
            if target_compose:  # Only validate for container projects
                target_services = target_compose.get("services", {})
                # Build full service name: {project}-{service}
                full_service_name = f"{target_project}-{target_service}"

                # Check if service exists (match both short and full name)
                if target_service not in target_services and full_service_name not in target_services:
                    errors.append(
                        f"egress target service '{target_service}' not found in "
                        f"project '{target_project}' (available services: "
                        f"{', '.join(target_services.keys())})"
                    )
        except Exception as e:  # pylint: disable=broad-exception-caught
            errors.append(f"Failed to load target project '{target_project}': {e}")

    return errors


def _validate_compose_schema(project_name: str) -> list[str]:
    """Validate docker-compose.yml against Docker Compose's own schema.

    Keyed on file presence (the container-project discriminator), not on
    parsed-content truthiness, so an empty or comments-only file is still
    schema-checked. Docker ships no supported Python-native Compose schema
    validator, so this shells out to the exact binary that would otherwise
    reject the file first at deploy time.
    """
    compose_file = root() / "projects" / project_name / "docker-compose.yml"
    if not compose_file.exists():
        return []

    try:
        # --no-interpolate decouples the schema verdict from decrypted secrets,
        # so validation stays runs-anywhere: a valid `${VAR:?required}` file
        # cannot false-fail on a machine without decryption keys.
        result = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "config", "--no-interpolate", "--quiet"],
            capture_output=True,
            text=True,
            timeout=COMPOSE_SCHEMA_CHECK_TIMEOUT,
            check=False,
        )
    except FileNotFoundError:
        # itsup validate is contractually runs-anywhere, including docker-less
        # GitOps machines; degrade to a logged skip rather than failing closed,
        # while the gate still holds wherever docker is present.
        logger.warning("docker CLI not found; skipped Compose schema validation for '%s'", project_name)
        return []
    except subprocess.TimeoutExpired:
        return [f"docker compose schema validation timed out for '{project_name}'"]

    if result.returncode != 0:
        return [f"{COMPOSE_SCHEMA_FAILURE_PREFIX}: {result.stderr.strip()}"]

    return []


def validate_project(project_name: str) -> list[str]:
    """Validate project configuration, return list of errors"""
    errors = _validate_compose_schema(project_name)

    try:
        compose, traefik = load_project(project_name)
    except Exception as e:
        errors.append(str(e))
        return errors

    # Skip service validation for external host passthroughs (no compose)
    if not compose:
        # External host passthrough - only validate that host is set
        if not traefik.host:
            errors.append("External host project must have 'host' field in itsup-project.yml")
        return errors

    # Validate ingress references exist in compose (for container projects)
    services = compose.get("services", {})
    for ingress in traefik.ingress:
        if ingress is None:
            continue
        if ingress.service not in services:
            errors.append(f"ingress references unknown service: {ingress.service}")

    # Validate static proxynet IPs declared on ingress rows
    errors.extend(_validate_ingress_ips(traefik))

    # Validate egress targets exist
    errors.extend(_validate_egress_targets(traefik))

    return errors


def validate_all() -> dict[str, list[str]]:
    """Validate all projects, return dict of project: [errors]"""
    results = {}
    ip_owner: dict[str, str] = {}
    for project in list_projects():
        errors = validate_project(project)

        # Detect proxynet IP collisions across projects (the only place with the global view)
        try:
            _, traefik = load_project(project)
            for ingress in traefik.ingress:
                if ingress and ingress.ipv4_address:
                    owner = ip_owner.get(ingress.ipv4_address)
                    if owner and owner != project:
                        errors.append(f"ipv4_address '{ingress.ipv4_address}' already claimed by project '{owner}'")
                    else:
                        ip_owner[ingress.ipv4_address] = project
        except Exception:  # pylint: disable=broad-exception-caught
            pass  # per-project load errors are already surfaced by validate_project

        if errors:
            results[project] = errors
    return results


def get_router_ip() -> str:
    """Get router IP from projects/itsup.yml or auto-detect"""

    # Try to load from projects/itsup.yml (top-level routerIP key)
    itsup_file = root() / "projects" / "itsup.yml"
    if itsup_file.exists():
        with open(itsup_file, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
            router_ip = config.get("routerIP")
            if router_ip:
                logger.info("Using router IP from projects/itsup.yml: %s", router_ip)
                return router_ip

    # Auto-detect using netifaces
    try:
        gateways = netifaces.gateways()
        router_ip = gateways["default"][netifaces.AF_INET][0]
        logger.info("Auto-detected router IP: %s", router_ip)

        # Write back to projects/itsup.yml since it was empty
        update_itsup_yml_router_ip(router_ip)

        return router_ip
    except Exception as e:
        logger.error("Could not auto-detect router IP and none configured in projects/itsup.yml: %s", e)
        raise ValueError("Router IP required: set in projects/itsup.yml or ensure network detection works") from e


def update_itsup_yml_router_ip(ip: str) -> None:
    """Update projects/itsup.yml with detected router IP"""
    itsup_file = root() / "projects" / "itsup.yml"

    if not itsup_file.exists():
        logger.warning("projects/itsup.yml not found, cannot update router IP")
        return

    # Read current content
    with open(itsup_file, encoding="utf-8") as f:
        content = f.read()

    # Replace the empty routerIP line with detected value
    updated = re.sub(
        r"(routerIP:)\s*$",
        f"routerIP: {ip}  # Auto-detected on {datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')}",
        content,
        flags=re.MULTILINE,
    )

    with open(itsup_file, "w", encoding="utf-8") as f:
        f.write(updated)

    logger.info("Updated projects/itsup.yml with router IP: %s", ip)


def get_trusted_ips() -> list[str]:
    """Build trusted IPs list for Traefik - Docker networks + router subnet"""
    router_ip = get_router_ip()
    return [f"{router_ip}/32"]


def load_itsup_config() -> dict[str, Any]:
    """Load projects/itsup.yml configuration

    Returns:
        Dictionary of itsUP configuration
        Secrets are left as ${VAR} placeholders - not expanded
    """
    itsup_file = root() / "projects" / "itsup.yml"

    if not itsup_file.exists():
        logger.warning("projects/itsup.yml not found, using defaults")
        return {}

    with open(itsup_file, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    # Secrets are left as ${VAR} for safety
    return config


def load_traefik_overrides() -> dict[str, Any]:
    """Load projects/traefik.yml override configuration

    Returns:
        Dictionary of Traefik configuration overrides
        Secrets are left as ${VAR} placeholders - not expanded
    """
    traefik_file = root() / "projects" / "traefik.yml"

    if not traefik_file.exists():
        logger.warning("projects/traefik.yml not found")
        return {}

    with open(traefik_file, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    # Secrets are left as ${VAR} for safety
    return config


def load_middleware_overrides() -> dict[str, Any]:
    """Load projects/middlewares.yml override configuration

    Returns:
        Dictionary of middleware configuration overrides
        Secrets are left as ${VAR} placeholders - not expanded
    """
    middleware_file = root() / "projects" / "middlewares.yml"

    if not middleware_file.exists():
        logger.warning("projects/middlewares.yml not found")
        return {}

    with open(middleware_file, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    # Secrets are left as ${VAR} for safety
    return config
