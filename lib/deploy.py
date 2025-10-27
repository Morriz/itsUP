"""
General-purpose deployment with zero-downtime rollout support

This module provides smart deployment functionality that works for any Docker Compose stack:
- DNS stack (dns/)
- Proxy stack (proxy/)
- Upstream projects (upstream/{project}/)

Key features:
- Config hash comparison to detect changes
- Zero-downtime rollout for stateless services
- Skip deployment if nothing changed
"""

import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from bin.write_artifacts import write_proxy_artifacts, write_upstream
from lib.data import get_env_with_secrets

logger = logging.getLogger(__name__)


def service_needs_update(compose_dir: str, service: str) -> bool:
    """Check if a service's image or config changed via hash comparison

    Args:
        compose_dir: Directory containing docker-compose.yml
        service: Service name to check

    Returns:
        True if service needs update, False if unchanged
    """
    try:
        # Get current config hash from docker-compose.yml
        result = subprocess.run(
            ["docker", "compose", "config", "--hash", service],
            cwd=compose_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        output = result.stdout.strip()

        if not output:
            logger.debug(f"No config hash output for {service} in {compose_dir}")
            return True

        # Output format: "service hash"
        parts = output.split()
        if len(parts) < 2:
            logger.debug(f"Unexpected hash output format for {service}: {output}")
            return True

        current_hash = parts[1]

        # Get project name from compose_dir (for container naming)
        project_name = Path(compose_dir).name if compose_dir != "proxy" and compose_dir != "dns" else compose_dir

        # Find running containers for this service
        container_filter = f"name={project_name}-{service}"
        result = subprocess.run(
            ["docker", "ps", "--filter", container_filter, "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=True,
        )

        containers = [c for c in result.stdout.strip().split("\n") if c]

        if not containers:
            logger.info(f"No running containers for {service} (filter: {container_filter})")
            return True  # Service not running, needs update

        # Get hash from first running container's label
        result = subprocess.run(
            [
                "docker",
                "inspect",
                containers[0],
                "--format",
                '{{index .Config.Labels "com.docker.compose.config-hash"}}',
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        running_hash = result.stdout.strip()

        if not running_hash:
            logger.debug(f"No config hash label on container {containers[0]}")
            return True

        if current_hash != running_hash:
            logger.info(f"{service} config changed: {running_hash[:12]} -> {current_hash[:12]}")
            return True

        logger.info(f"{service} config unchanged ({current_hash[:12]})")
        return False

    except subprocess.CalledProcessError as e:
        logger.warning(f"Error checking {service} update status: {e}")
        return True  # On error, assume update needed
    except Exception as e:
        logger.warning(f"Unexpected error checking {service}: {e}")
        return True


def rollout_service(compose_dir: str, service: str) -> None:
    """Perform zero-downtime rollout for a stateless service

    Uses docker-rollout plugin to:
    1. Scale up to 2x instances
    2. Wait for new instances to be healthy
    3. Kill old instances
    4. Scale back to 1x

    Args:
        compose_dir: Directory containing docker-compose.yml
        service: Service name to rollout

    Raises:
        subprocess.CalledProcessError: If rollout fails
    """
    logger.info(f"Rolling out {service} from {compose_dir} (zero downtime)")

    try:
        subprocess.run(["docker", "rollout", service], cwd=compose_dir, check=True)
        logger.info(f"✓ {service} rolled out successfully")
    except subprocess.CalledProcessError as e:
        logger.error(f"✗ {service} rollout failed: {e}")
        raise


def smart_deploy(
    compose_dir: str,
    compose_file: str = "docker-compose.yml",
    stateless_services: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
    service_filter: Optional[str] = None,
) -> None:
    """Deploy a Docker Compose stack with smart rollout for stateless services

    Process:
    1. Pull latest images
    2. Deploy with docker compose up -d
    3. For each stateless service:
       - Check if config changed (hash comparison)
       - If changed: perform zero-downtime rollout
       - If unchanged: skip rollout

    Args:
        compose_dir: Directory containing docker-compose.yml
        compose_file: Name of compose file (default: docker-compose.yml)
        stateless_services: List of service names that are stateless and safe for rollout
        env: Environment variables to pass to docker compose
        service_filter: Optional service name to deploy (if None, deploys all)

    Example:
        # Deploy proxy stack with traefik as stateless
        smart_deploy(
            "proxy",
            stateless_services=["traefik"],
            env=get_env_with_secrets()
        )

        # Deploy upstream project with web service as stateless
        smart_deploy(
            "upstream/myapp",
            stateless_services=["web"],
            env=get_env_with_secrets("myapp")
        )
    """
    if stateless_services is None:
        stateless_services = []

    logger.info(f"Deploying {compose_dir}..." + (f" (service: {service_filter})" if service_filter else ""))

    # Pull images
    pull_cmd = ["docker", "compose", "-f", f"{compose_dir}/{compose_file}", "pull"]
    if service_filter:
        pull_cmd.append(service_filter)

    logger.info(f"Pulling images for {compose_dir}...")
    subprocess.run(pull_cmd, env=env, check=False)  # Don't fail on pull errors (local images)

    # Deploy with docker compose up -d
    up_cmd = ["docker", "compose", "-f", f"{compose_dir}/{compose_file}", "up", "-d"]
    if service_filter:
        up_cmd.append(service_filter)

    logger.info(f"Starting services in {compose_dir}...")
    subprocess.run(up_cmd, env=env, check=True)

    # Rollout stateless services for zero downtime
    if stateless_services:
        logger.info(f"Checking stateless services for rollout: {', '.join(stateless_services)}")

        for service in stateless_services:
            # Skip if specific service requested and this isn't it
            if service_filter and service != service_filter:
                continue

            # Check if service needs update (skip if unchanged)
            if not service_needs_update(compose_dir, service):
                logger.info(f"Skipping rollout for {service} (no changes)")
                continue

            # Perform zero-downtime rollout
            try:
                rollout_service(compose_dir, service)
            except subprocess.CalledProcessError:
                logger.error(f"Failed to rollout {service}, but continuing...")
                # Don't fail entire deployment if rollout fails
    else:
        logger.debug(f"No stateless services configured for {compose_dir}")


# Stack-specific deployment helpers


def deploy_dns_stack(service: Optional[str] = None) -> None:
    """Deploy DNS stack with smart rollout

    DNS services that are stateless: dns-honeypot (if stateless)
    """
    smart_deploy(
        compose_dir="dns",
        stateless_services=[],  # DNS services typically not stateless (has state/logs)
        env=get_env_with_secrets(),
        service_filter=service,
    )


def deploy_proxy_stack(service: Optional[str] = None) -> None:
    """Deploy proxy stack with smart rollout

    Stateless services: traefik
    Stateful services: dockerproxy, dns (fast restart ok)
    """
    # Always regenerate proxy artifacts (templates depend on projects/)
    write_proxy_artifacts()

    # Deploy with rollout for traefik only
    smart_deploy(
        compose_dir="proxy",
        stateless_services=["traefik"],  # Only traefik is stateless
        env=get_env_with_secrets(),
        service_filter=service,
    )


def deploy_upstream_project(project: str, service: Optional[str] = None) -> None:
    """Deploy upstream project with smart rollout

    Automatically detects stateless services using convention:
    - Services WITHOUT volumes are stateless (safe for rollout)
    - Services WITH volumes are stateful (normal restart)

    Args:
        project: Project name
        service: Optional service name to deploy
    """
    # Regenerate artifacts
    logger.info(f"Regenerating {project} config...")
    write_upstream(project)

    # Read generated docker-compose.yml to detect stateless services
    compose_path = Path(f"upstream/{project}/docker-compose.yml")
    try:
        with open(compose_path, encoding="utf-8") as f:
            compose = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load {compose_path}: {e}")
        raise

    # Detect stateless services: those WITHOUT volumes
    # Exception: traefik has volumes (logs/acme/config) but we treat it as stateless
    # for zero-downtime rollouts. Assumptions we accept:
    # - ACME cert conflicts are rare during brief rollout window
    # - Log interleaving is acceptable trade-off for zero downtime
    # - Config files are read-only (safe to share)
    stateless_services = []
    for service_name, service_config in compose.get("services", {}).items():
        volumes = service_config.get("volumes", [])
        if not volumes or service_name == "traefik":
            stateless_services.append(service_name)

    if stateless_services:
        logger.info(f"Stateless services in {project}: {', '.join(stateless_services)}")
    else:
        logger.debug(f"No stateless services in {project}")

    # Deploy with smart rollout
    smart_deploy(
        compose_dir=f"upstream/{project}",
        stateless_services=stateless_services,
        env=get_env_with_secrets(project),
        service_filter=service,
    )
