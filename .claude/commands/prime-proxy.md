# Prime Context: Proxy Infrastructure

You are now working on the **proxy infrastructure** for this system.

## Architecture Overview

This system uses a **template-based proxy generation** paradigm:

1. **Source of Truth**: `projects/` directory with per-project `docker-compose.yml` and `ingress.yml` files
2. **Infrastructure Config**: `projects/itsup.yml` and `projects/traefik.yml` for infrastructure settings
3. **Code Generation**: Python templates in `tpl/` generate:
   - `proxy/docker-compose.yml` - Traefik stack configuration
   - `proxy/traefik/traefik.yml` - Traefik static configuration (merged with user overrides)
   - `proxy/traefik/dynamic/*.yml` - Dynamic routing rules
   - `upstream/{project}/docker-compose.yml` - Per-project service configs with Traefik labels
4. **Zero-Downtime Deployment**:
   - Stateless services (traefik, crowdsec) use `docker-rollout`
   - Infrastructure services (dockerproxy, dns) restart normally

## Key Components

### Traefik Stack

- **traefik**: Reverse proxy with Let's Encrypt, listens on ports 8080 (http) and 8443 (https)
- **dockerproxy**: Secure Docker socket proxy (minimal permissions)
- **dns**: DNS honeypot at 172.20.0.253 for logging
- **crowdsec**: Security plugin for threat detection

### Routing Modes

- **HTTP/HTTPS**: Domain-based routing with automatic TLS via Let's Encrypt
- **TCP**: SNI-based routing for raw TCP (databases, VPN)
- **UDP**: Port-based routing (VPN)

### Discovery Methods

1. **Dynamic Labels** (preferred): Services with `ingress.domain` get Traefik labels auto-generated
2. **Static File Routers**: Services with `ingress.hostport` or `passthrough` get static config files

## Critical Files to Read

**Start here** to understand the proxy system:

1. **bin/write_artifacts.py** - Proxy and upstream artifact generation

   - `write_proxy_compose()` - Generate proxy/docker-compose.yml
   - `write_traefik_config()` - Generate proxy/traefik/traefik.yml
   - `write_dynamic_routers()` - Generate dynamic routing configs
   - `write_proxy_artifacts()` - Master function for all proxy generation
   - `inject_traefik_labels()` - Generate Traefik labels from ingress.yml

2. **tpl/proxy/docker-compose.yml.j2** - Compose template

   - Service definitions for traefik, dockerproxy, dns, crowdsec
   - Healthcheck patterns
   - Dependency graph

3. **tpl/proxy/traefik.yml.j2** - Traefik static config template

   - Entry points (web, web-secure, tcp/udp hostports)
   - Let's Encrypt configuration
   - Provider settings (Docker, file)

4. **tpl/proxy/routers-{http,tcp,udp}.yml.j2** - Dynamic routing templates

   - Router and service definitions for static routes
   - Middleware chains

5. **lib/models.py** - IngressV2 model definition

   - TLS SANs support
   - Ingress entry structure

6. **README.md** - Project documentation
   - Sections: "Proxy Stack", "Service Deployment", "Routing"

## Key Concepts

### Stateless Services (use docker-rollout)

- **traefik**: Main reverse proxy
- **crowdsec**: Security plugin
- Can scale to 2x instances safely during rollout

### Infrastructure Services (restart normally)

- **dockerproxy**: Socket proxy (1ms startup)
- **dns**: DNS honeypot (fast restart)
- Cannot use rollout (no meaningful state)

### Healthchecks

- **dockerproxy**: `./healthcheck` binary (requires `-allowhealthcheck` flag)
- **traefik**: `traefik healthcheck` command
- All include `/tmp/drain` check for docker-rollout compatibility

### Update Flow

```
projects/ change → itsup apply → write_artifacts.py → docker compose up -d → rollout stateless services
```

## Common Tasks

**Regenerate proxy config**:

```bash
python3 bin/write_artifacts.py  # Generates all configs
docker compose -f proxy/docker-compose.yml config --quiet  # Validate
```

**Update proxy with rollout**:

```bash
itsup apply  # Smart update with change detection for all projects
itsup apply traefik  # Smart update for proxy only
# OR manually:
itsup svc traefik up  # Direct docker compose passthrough
```

**Debug routing**:

- Check `proxy/traefik/dynamic/*.yml` for static routes
- `docker logs proxy-traefik-X` for dynamic label discovery
- Traefik dashboard: https://traefik.srv.instrukt.ai (if configured)

## Important Constraints

1. **Never modify generated files directly** - Always edit templates in `tpl/` or project configs in `projects/`
2. **Validate YAML** after template changes with `docker compose config --quiet`
3. **Only stateless services use docker-rollout** - Check `STATELESS_SERVICES` constant in bin/write_artifacts.py
4. **Hostport services need static routers** - They bypass dynamic label discovery

## Ready to Work

You are now primed to work on the proxy infrastructure. Read the files above in order, then ask any questions about the specific task.
