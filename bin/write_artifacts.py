import os
import shutil
import sys
from io import StringIO
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from instrukt_ai_logging import configure_logging, get_logger
from jinja2 import Template
from ruamel.yaml import YAML

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.data import (
    build_reverse_egress_graph,
    edge_network_name,
    get_trusted_ips,
    list_projects,
    load_itsup_config,
    load_middleware_overrides,
    load_project,
    load_secrets,
    load_traefik_overrides,
    validate_all,
)
from lib.models import ACME_CHALLENGE_PATH_PREFIX, ProxyProtocol, TraefikConfig
from lib.paths import root

load_dotenv()

logger = get_logger(f"itsup.{__name__}")

# DNS honeypot for logging (used by all containers)
DNS_HONEYPOT = "172.20.0.253"


def write_file_if_changed(file_path: Path, content: str, description: str = None) -> bool:
    """Write file only if content changed. Returns True if file was written.

    Args:
        file_path: Path to file
        content: New content to write
        description: Optional description for logging

    Returns:
        True if file was written (changed or new), False if skipped (unchanged)
    """
    desc = description or str(file_path)

    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            old_content = f.read()

        if old_content == content:
            logger.debug(f"Skipping {desc} (unchanged)")
            return False

    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Write file (content changed or doesn't exist)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"Generated {desc}")
    return True


def sync_project_files(project_name: str) -> None:
    """Mirror a project's deployable files into its generated upstream directory."""
    source = root() / "projects" / project_name / "files"
    destination = root() / "upstream" / project_name / "files"

    if destination.exists():
        shutil.rmtree(destination)

    if source.exists():
        shutil.copytree(source, destination)


def inject_traefik_labels(
    compose: dict[str, Any],  # guard: loose-dict - arbitrary docker-compose mapping
    traefik_config: TraefikConfig,
    project_name: str,
) -> dict[str, Any]:  # guard: loose-dict - arbitrary docker-compose mapping
    """Inject Traefik labels into docker-compose services based on traefik.yml"""
    if not traefik_config.enabled:
        return compose

    services = compose.get("services", {})

    for ingress in traefik_config.ingress:
        service_name = ingress.service
        if service_name not in services:
            logger.warning(f"Service {service_name} in traefik.yml not found in docker-compose.yml")
            continue

        # Initialize labels if not present
        if "labels" not in services[service_name]:
            services[service_name]["labels"] = []

        labels = services[service_name]["labels"]
        if isinstance(labels, dict):
            # Convert dict to list format
            labels = [f"{k}={v}" for k, v in labels.items()]
            services[service_name]["labels"] = labels

        # Build Traefik labels
        # Make router name unique by including port to handle multiple ingress entries for same service
        router_name = f"{project_name}-{service_name}-{ingress.port}"

        # Enable Traefik (only once per service, not per ingress)
        if "traefik.enable=true" not in labels:
            labels.append("traefik.enable=true")

        # Router configuration
        if ingress.router == "http":
            # HTTP router
            labels.append(f"traefik.http.routers.{router_name}.entrypoints=web-secure")

            # Domain-based rule
            domains = []
            if ingress.tls and ingress.tls.main:
                # TLS with main + SANs
                domains = [ingress.tls.main] + ingress.tls.sans
            elif ingress.domain:
                # Legacy domain field
                domains = [ingress.domain]

            if domains:
                rule = " || ".join([f"Host(`{d}`)" for d in domains])
                if ingress.path_prefix:
                    rule += f" && PathPrefix(`{ingress.path_prefix}`)"
                labels.append(f"traefik.http.routers.{router_name}.rule={rule}")
                labels.append(f"traefik.http.routers.{router_name}.service={router_name}")
                labels.append(f"traefik.http.routers.{router_name}.tls=true")
                labels.append(f"traefik.http.routers.{router_name}.tls.certresolver=letsencrypt")

                # TLS domain configuration with SANs
                if ingress.tls and ingress.tls.main:
                    labels.append(f"traefik.http.routers.{router_name}.tls.domains[0].main={ingress.tls.main}")
                    if ingress.tls.sans:
                        sans = ",".join(ingress.tls.sans)
                        labels.append(f"traefik.http.routers.{router_name}.tls.domains[0].sans={sans}")

                # Companion plain-HTTP router: redirect to HTTPS. Traefik's ACME
                # HTTP-01 challenge handling on the `web` entrypoint intercepts
                # /.well-known/acme-challenge/* ahead of router matching, so this
                # can't interfere with certificate issuance/renewal — except for
                # the narrow passthrough-ACME-forwarding carve-out, which must
                # reach the backend unredirected.
                if ingress.path_prefix != ACME_CHALLENGE_PATH_PREFIX:
                    redirect_router = f"{router_name}-redirect"
                    labels.append(f"traefik.http.routers.{redirect_router}.entrypoints=web")
                    labels.append(f"traefik.http.routers.{redirect_router}.rule={rule}")
                    labels.append(f"traefik.http.routers.{redirect_router}.service={router_name}")
                    labels.append(f"traefik.http.routers.{redirect_router}.middlewares=redirect@file")

            # Service port
            labels.append(f"traefik.http.services.{router_name}.loadbalancer.server.port={ingress.port}")

            # Path-prefix stripping middleware is not generated here; the
            # ingress `path_remove` field is not currently wired into label output.

        # We DON'T do this for tcp and udp as those need other port and thus new entrypoints MUST be made in traefik.yml
        # We decided to be explicit+consistent and generate the entrypoints AND the routers (this needs `itsup apply proxy` anyway)
        # elif ingress.router == "tcp":
        #     # TCP router
        #     labels.append(f"traefik.tcp.routers.{router_name}.entrypoints=tcp-{ingress.hostport or ingress.port}")
        #     labels.append(f"traefik.tcp.routers.{router_name}.rule=HostSNI(`*`)")

        #     if ingress.passthrough:
        #         labels.append(f"traefik.tcp.routers.{router_name}.tls.passthrough=true")
        #     else:
        #         labels.append(f"traefik.tcp.routers.{router_name}.tls=true")

        #     labels.append(f"traefik.tcp.services.{router_name}.loadbalancer.server.port={ingress.port}")

        # elif ingress.router == "udp":
        #     # UDP router
        #     labels.append(f"traefik.udp.routers.{router_name}.entrypoints=udp-{ingress.hostport or ingress.port}")
        #     labels.append(f"traefik.udp.services.{router_name}.loadbalancer.server.port={ingress.port}")

    return compose


def write_upstream(project_name: str, reverse_graph: dict[str, list[tuple[str, str]]] | None = None) -> None:
    """Generate upstream/{project}/docker-compose.yml with Traefik labels injected"""
    logger.info(f"Generating upstream config for {project_name}")

    # Load project from projects/
    compose, traefik = load_project(project_name)

    # Skip docker-compose.yml generation for host-only projects (no services)
    if not compose or not compose.get("services"):
        logger.info(f"✓ {project_name} is host-only (no services), skipping docker-compose.yml generation")
        return

    # Inject Traefik labels
    compose = inject_traefik_labels(compose, traefik, project_name)

    # Merge proxynet network (required for Traefik discovery)
    if "networks" not in compose:
        compose["networks"] = {}

    # Add proxynet if not already present
    if "proxynet" not in compose["networks"]:
        compose["networks"]["proxynet"] = {"external": True}

    # Network segmentation based on ingress/egress declarations
    services = compose.get("services", {})

    # Collect per-service overrides declared on ingress rows.
    # Both are per-container concerns; an ingress row is the only per-service input surface.
    static_ips: dict[str, str] = {}
    dns_overrides: dict[str, list[str]] = {}
    for ing in traefik.ingress:
        if ing is None or not ing.service:
            continue
        if ing.ipv4_address:
            static_ips[ing.service] = ing.ipv4_address
        if ing.dns:
            dns_overrides[ing.service] = ing.dns

    # Snapshot which services declared explicit networks before Phase 1 normalises them.
    # Phase 2b uses this to preserve default-network sibling reachability for provider services
    # that did not opt out of the implicit default network.
    _explicit_networks = {svc for svc, cfg in services.items() if "networks" in cfg}

    # Phase 1: Configure service networks and DNS
    for service_name, service_config in services.items():
        # Initialize networks if not present
        if "networks" not in service_config:
            service_config["networks"] = []

        # Convert dict format to list if needed
        if isinstance(service_config["networks"], dict):
            service_config["networks"] = list(service_config["networks"].keys())

        # Add proxynet ONLY if service has ingress (Traefik needs access)
        labels = service_config.get("labels", [])
        has_traefik = any("traefik.enable=true" in str(label) for label in labels)

        if has_traefik and "proxynet" not in service_config["networks"]:
            service_config["networks"].append("proxynet")

        # An explicit dns override declared on ingress is written verbatim,
        # replacing the default honeypot injection (the guard below yields to it).
        if service_name in dns_overrides:
            service_config["dns"] = dns_overrides[service_name]

        # Inject DNS honeypot into all services (for logging)
        # Add Docker DNS (127.0.0.11) as fallback for internal name resolution
        if "dns" not in service_config:
            service_config["dns"] = [DNS_HONEYPOT, "127.0.0.11"]

    # Phase 2: Add per-edge consumer networks.
    # Each egress declaration gets a dedicated edge network shared only between
    # this project and the specific provider service — no {target}_default join,
    # no co-consumer reachability, no access to other provider services.
    for egress_spec in traefik.egress:
        if ":" not in egress_spec:
            logger.warning(f"Invalid egress format: {egress_spec} (expected: project:service)")
            continue

        target_project, target_service = egress_spec.split(":", 1)
        edge_net = edge_network_name(project_name, target_project, target_service)

        if edge_net not in compose["networks"]:
            compose["networks"][edge_net] = {"external": True}

        for service_name, service_config in services.items():
            if edge_net not in service_config["networks"]:
                service_config["networks"].append(edge_net)

    # Phase 2b: Provider side — create edge networks for each declared consumer.
    # Only the named provider service is attached; the consumer joins as external.
    if reverse_graph is None:
        reverse_graph = build_reverse_egress_graph()

    for consumer, svc_name in reverse_graph.get(project_name, []):
        edge_net = edge_network_name(consumer, project_name, svc_name)

        # Resolve the actual service key (consumer may use short or prefixed name)
        actual_key = svc_name if svc_name in services else f"{project_name}-{svc_name}"
        if actual_key not in services:
            logger.warning(f"Edge net {edge_net}: service '{svc_name}' not found in provider {project_name}; skipping")
            continue

        if edge_net not in compose["networks"]:
            # Not external — this project creates the network with an explicit Docker name
            # so the consumer can reference it as external without the compose project prefix.
            compose["networks"][edge_net] = {"name": edge_net}

        svc_nets = services[actual_key].get("networks", [])
        if edge_net not in svc_nets:
            svc_nets.append(edge_net)
            # Preserve sibling reachability: services that didn't opt out of the implicit
            # default network need it listed explicitly once the networks key is set.
            if actual_key not in _explicit_networks and "default" not in svc_nets:
                svc_nets.append("default")
            services[actual_key]["networks"] = svc_nets

    # Phase 3: Pin static proxynet IPs.
    # docker compose requires the whole networks block in mapping form once any
    # entry carries options, so convert that service's list to a mapping with
    # ipv4_address on proxynet and bare (default-option) entries for the rest.
    for service_name, ip in static_ips.items():
        service_config = services.get(service_name)
        if not service_config:
            continue

        nets = service_config.get("networks", [])
        net_names = list(nets.keys()) if isinstance(nets, dict) else list(nets)

        if "proxynet" not in net_names:
            logger.warning(
                f"ipv4_address {ip} declared for {project_name}/{service_name} "
                f"but the service is not on proxynet; ignoring"
            )
            continue

        service_config["networks"] = {name: {"ipv4_address": ip} if name == "proxynet" else None for name in net_names}

    # Write docker-compose.yml (only if changed to avoid triggering unnecessary deployments)
    compose_file = root() / "upstream" / project_name / "docker-compose.yml"
    content = yaml.dump(
        compose,
        indent=2,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=float("inf"),
    )
    sync_project_files(project_name)
    write_file_if_changed(compose_file, content)


def write_upstreams() -> bool:
    """Generate all upstream/* directories from projects/

    Returns: True if all projects succeeded, False if any failed
    """
    projects = list_projects()

    if not projects:
        logger.warning("No projects found in projects/ directory")
        return True

    # Build the reverse graph once so each provider knows its consumers.
    reverse_graph = build_reverse_egress_graph()

    failed_projects = []
    for project_name in projects:
        try:
            write_upstream(project_name, reverse_graph)
        except Exception as e:
            logger.error(f"Failed to generate upstream for {project_name}: {e}")
            failed_projects.append(project_name)

    if failed_projects:
        logger.error(f"Failed to generate upstream configs for: {', '.join(failed_projects)}")
        return False

    return True


def deep_merge(
    base: dict[str, Any],  # guard: loose-dict - arbitrary YAML config merge
    override: dict[str, Any],  # guard: loose-dict - arbitrary YAML config merge
) -> dict[str, Any]:  # guard: loose-dict - arbitrary YAML config merge
    """Deep merge override dict into base dict"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def write_traefik_config() -> None:
    """Generate proxy/traefik/traefik.yml from minimal template + user overrides"""
    logger.info("Generating proxy/traefik/traefik.yml")

    # Get trusted IPs for template
    trusted_ips_cidrs = get_trusted_ips()
    crowdsec_enabled = load_itsup_config().get("crowdsec", {}).get("enabled", False)

    # Load all projects to collect TCP/UDP entrypoints
    projects_data = []
    for project_name in list_projects():
        _, traefik_config = load_project(project_name)
        if traefik_config.enabled and traefik_config.ingress:
            # Only include projects with TCP/UDP ingress
            tcp_udp_ingress = []
            for i in traefik_config.ingress:
                if i.router not in ("tcp", "udp"):
                    continue
                # Passthrough WITHOUT hostport reuses the existing web-secure entrypoint
                # (no new entrypoint to generate). Passthrough WITH hostport (e.g. :443 for
                # an SNI-routed broker) still needs its own entrypoint declared here.
                if i.passthrough and not i.hostport:
                    continue
                # Convert to dict with string values for template
                tcp_udp_ingress.append(
                    {
                        "service": i.service,
                        "router": str(i.router.value) if hasattr(i.router, "value") else str(i.router),
                        "protocol": str(i.protocol.value) if hasattr(i.protocol, "value") else str(i.protocol),
                        "port": i.port,
                        "hostport": i.hostport,
                    }
                )
            if tcp_udp_ingress:
                projects_data.append({"name": project_name, "ingress": tcp_udp_ingress})

    # Load minimal template
    with open(root() / "tpl" / "traefik.yml.j2", encoding="utf-8") as f:
        template_content = f.read()

    template = Template(template_content)

    # Render minimal base config (structure + trustedIPs + dynamic entrypoints)
    config_content = template.render(
        trusted_ips_cidrs=trusted_ips_cidrs,
        projects=projects_data,
        crowdsec_enabled=crowdsec_enabled,
    )

    # Parse generated base config using ruamel.yaml to preserve comments
    ryaml = YAML()
    ryaml.preserve_quotes = True
    ryaml.default_flow_style = False
    ryaml.width = 4096  # Avoid line wrapping

    base_config = ryaml.load(StringIO(config_content))

    # Load user overrides from projects/traefik.yml
    override_config = load_traefik_overrides()

    if override_config:
        logger.info("Merging user overrides from projects/traefik.yml")
        # Deep merge overrides ON TOP of base
        final_config = deep_merge(base_config, override_config)
    else:
        logger.warning("No projects/traefik.yml found - using minimal config only")
        final_config = base_config

    # Traefik expands {{ env "VAR" }} at runtime from environment
    # Variables are left as-is for Traefik to process

    # Write final config (only if changed) using ruamel.yaml to preserve comments
    traefik_config_file = root() / "proxy" / "traefik" / "traefik.yml"
    output = StringIO()
    ryaml.dump(final_config, output)
    content = output.getvalue()
    write_file_if_changed(traefik_config_file, content, "proxy/traefik/traefik.yml")


def write_middleware_config() -> None:
    """Generate proxy/traefik/dynamic/middlewares.yml from template + user overrides"""
    logger.info("Generating proxy/traefik/dynamic/middlewares.yml")

    # Load itsUP config for CrowdSec settings
    itsup_config = load_itsup_config()
    crowdsec_config = itsup_config.get("crowdsec", {})

    # Load secrets for template variables
    secrets = load_secrets()  # itsUP infrastructure secrets

    # Validate required secrets
    if "TRAEFIK_ADMIN" not in secrets:
        raise ValueError(
            "Missing required secret: TRAEFIK_ADMIN\n"
            "Add to secrets/itsup.txt or secrets/itsup.enc.txt\n"
            "Generate with: htpasswd -nb admin your-password"
        )

    # Load minimal template
    with open(root() / "tpl" / "middlewares.yml.j2", encoding="utf-8") as f:
        template_content = f.read()

    template = Template(template_content)

    # Render minimal base config
    config_content = template.render(
        traefik_admin=secrets["TRAEFIK_ADMIN"],
        trusted_ips_cidrs=get_trusted_ips(),
        crowdsec={
            "enabled": crowdsec_config.get("enabled", False),
            "apikey": crowdsec_config.get("apikey", ""),
        },
    )

    # Parse generated base config using ruamel.yaml to preserve comments
    ryaml = YAML()
    ryaml.preserve_quotes = True
    ryaml.default_flow_style = False
    ryaml.width = 4096  # Avoid line wrapping

    base_config = ryaml.load(StringIO(config_content))

    # Load user overrides from projects/middlewares.yml
    override_config = load_middleware_overrides()

    if override_config:
        logger.info("Merging user overrides from projects/middlewares.yml")
        # Deep merge overrides ON TOP of base
        final_config = deep_merge(base_config, override_config)
    else:
        logger.warning("No projects/middlewares.yml found - using minimal config only")
        final_config = base_config

    # Write final config (only if changed) using ruamel.yaml to preserve comments
    middleware_config_file = root() / "proxy" / "traefik" / "dynamic" / "middlewares.yml"
    output = StringIO()
    ryaml.dump(final_config, output)
    content = output.getvalue()
    write_file_if_changed(middleware_config_file, content, "middlewares.yml")


def write_dynamic_routers() -> None:
    """Generate dynamic Traefik router configs"""
    logger.info("Generating dynamic router configs")

    # Load itsUP config for traefik domain
    itsup_config = load_itsup_config()
    traefikDomain = itsup_config.get("traefikDomain", {})
    if not traefikDomain:
        raise ValueError(
            "Missing required config: projects/itsup.yml must have 'traefikDomain' field\n"
            "Example:\n"
            "  traefik:\n"
            "    domain: traefik.example.com"
        )

    # Load secrets for template variables
    secrets = load_secrets()  # itsUP infrastructure secrets

    # Validate required secrets
    if "TRAEFIK_ADMIN" not in secrets:
        raise ValueError(
            "Missing required secret: TRAEFIK_ADMIN\n"
            "Add to secrets/itsup.txt or secrets/itsup.enc.txt\n"
            "Generate with: htpasswd -nb admin your-password"
        )

    # crowdsec config lives at the top level of itsup.yml (no plugin_registry)

    # Build project list in V1 format for templates
    all_project_names = list_projects()
    all_projects = []

    for project_name in all_project_names:
        compose, traefik = load_project(project_name)

        # Skip disabled projects
        if not traefik.enabled:
            continue

        # Include projects with ingress config (both external hosts and containers)
        # External hosts: no compose, but have traefik.host
        # Containers: have compose, may have ingress for passthrough/hostport
        if traefik.host:  # External host
            all_projects.append(
                {
                    "name": project_name,
                    "external": True,
                    "services": [{"host": traefik.host, "ingress": traefik.ingress}],
                }
            )
        elif any(
            i.hostport or i.passthrough or i.protocol not in ["http", "https"] for i in traefik.ingress
        ):  # Container with hostport/passthrough
            services = []
            for i in traefik.ingress:
                if not (i.hostport or i.passthrough or i.protocol not in ["http", "https"]):
                    continue
                # When the container has a pinned proxynet IP, Traefik (on the host
                # network) can reach it directly by that IP — no name resolution needed.
                # Otherwise fall back to the service name, which only works if it's
                # resolvable from Traefik's network namespace.
                backend_host = i.ipv4_address or i.service
                services.append({"host": backend_host, "ingress": [i]})
            all_projects.append({"name": project_name, "external": False, "services": services})

    # Filter by router type for templates
    projects_http = []
    projects_tcp = []
    projects_udp = []

    for p in all_projects:
        http_services = []
        tcp_services = []
        udp_services = []

        for s in p["services"]:
            # Containers route plain HTTP via Traefik labels, so a container only
            # needs a dynamic-file HTTP router when it declares a hostport (a
            # dedicated entrypoint). External hosts have no labels, so they must
            # always get the dynamic-file router — routed on web-secure to
            # host:port — regardless of hostport.
            http_ingress = [
                i
                for i in s["ingress"]
                if (not i.router or i.router == "http")
                and (p["external"] or (i.hostport and i.hostport not in (8080, 8443)))
            ]
            tcp_ingress = [i for i in s["ingress"] if i.router == "tcp"]
            udp_ingress = [i for i in s["ingress"] if i.router == "udp"]

            if http_ingress:
                http_services.append({"host": s["host"], "ingress": http_ingress})
            if tcp_ingress:
                tcp_services.append({"host": s["host"], "ingress": tcp_ingress})
            if udp_ingress:
                udp_services.append({"host": s["host"], "ingress": udp_ingress})

        if http_services:
            projects_http.append({"name": p["name"], "services": http_services})
        if tcp_services:
            projects_tcp.append({"name": p["name"], "services": tcp_services})
        if udp_services:
            projects_udp.append({"name": p["name"], "services": udp_services})

    # Render HTTP routers using full template
    with open(root() / "tpl" / "routers-http.yml.j2", encoding="utf-8") as f:
        template_content = f.read()

    tpl_routers_http = Template(template_content)

    routers_http = tpl_routers_http.render(
        projects=projects_http,
        traefik_admin=secrets["TRAEFIK_ADMIN"],
        traefik_rule=f"Host(`{traefikDomain}`)",
        trusted_ips_cidrs=get_trusted_ips(),
    )

    # Render TCP routers using full template
    with open(root() / "tpl" / "routers-tcp.yml.j2", encoding="utf-8") as f:
        template_content = f.read()

    tpl_routers_tcp = Template(template_content)
    tpl_routers_tcp.globals["ProxyProtocol"] = ProxyProtocol  # Make enum available to template
    routers_tcp = tpl_routers_tcp.render(
        projects=projects_tcp,
    )

    # Render UDP routers
    with open(root() / "tpl" / "routers-udp.yml.j2", encoding="utf-8") as f:
        template_content = f.read()

    tpl_routers_udp = Template(template_content)
    routers_udp = tpl_routers_udp.render(
        projects=projects_udp,
    )

    # Write router files (only if changed)
    http_file = root() / "proxy" / "traefik" / "dynamic" / "routers-http.yml"
    tcp_file = root() / "proxy" / "traefik" / "dynamic" / "routers-tcp.yml"
    udp_file = root() / "proxy" / "traefik" / "dynamic" / "routers-udp.yml"

    http_changed = write_file_if_changed(http_file, routers_http, "routers-http.yml")
    tcp_changed = write_file_if_changed(tcp_file, routers_tcp, "routers-tcp.yml")
    udp_changed = write_file_if_changed(udp_file, routers_udp, "routers-udp.yml")

    if http_changed or tcp_changed or udp_changed:
        logger.info(f"Generated dynamic routers for {len(all_projects)} external host projects")


def write_proxy_compose() -> None:
    """Generate proxy/docker-compose.yml from template"""
    logger.info("Generating proxy/docker-compose.yml")

    # Load versions from itsup.yml (top-level versions key)
    itsup_config = load_itsup_config()

    # Build template context
    context = {
        "dns_honeypot": DNS_HONEYPOT,
        "itsup": itsup_config,
    }

    with open(root() / "tpl" / "docker-compose.yml.j2", encoding="utf-8") as f:
        template_content = f.read()

    template = Template(template_content)
    compose_content = template.render(**context)

    # Write compose file (only if changed)
    proxy_compose_file = root() / "proxy" / "docker-compose.yml"
    write_file_if_changed(proxy_compose_file, compose_content, "proxy/docker-compose.yml")


def write_proxy_artifacts() -> None:
    """Generate all proxy-related artifacts"""
    write_traefik_config()
    write_middleware_config()  # Dynamic middlewares (base + overrides)
    write_dynamic_routers()  # Dynamic routers (infrastructure + external hosts)
    write_proxy_compose()


if __name__ == "__main__":
    os.environ["ITSUP_LOG_LEVEL"] = os.getenv("LOG_LEVEL", "INFO")
    configure_logging("itsup")

    # Validate all projects first
    errors = validate_all()
    if errors:
        logger.error("Validation errors found:")
        for project, project_errors in errors.items():
            for error in project_errors:
                logger.error(f"  {project}: {error}")
        sys.exit(1)

    # Generate proxy artifacts (traefik config, routers, docker-compose)
    logger.info("Generating proxy artifacts...")
    write_proxy_artifacts()

    # Generate upstream configs
    logger.info("Generating upstream configs...")
    if not write_upstreams():
        logger.error("Failed to generate some upstream configs")
        sys.exit(1)

    logger.info("✅ All artifacts generated successfully")
