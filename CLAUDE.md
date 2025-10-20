# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

**itsUP** is a lean, automated, poor man's infrastructure automation tool for managing Docker-based services with zero-downtime deployments. It provides a single source of truth (`db.yml`) for defining projects and services, which it then translates into Traefik-based proxy configurations and Docker Compose deployments.

### Core Architecture

The system has three main layers:

1. **Configuration Layer** (`db.yml`): Single source of truth defining all projects, services, ingress rules, and plugins
2. **Generation Layer** (`lib/`): Python modules that read `db.yml` and generate Docker Compose files and Traefik configurations
3. **Deployment Layer**: Docker Compose orchestration with Traefik for routing and optional zero-downtime rollouts via `docker rollout` plugin

### Key Components

- **`lib/data.py`**: Database operations - reads/writes/validates `db.yml`, manages projects/services/plugins with Pydantic models
- **`lib/models.py`**: Pydantic models defining the schema for Projects, Services, Ingress, Plugins, etc.
- **`lib/proxy.py`**: Generates Traefik configurations (routers, middleware, TLS) and proxy's `docker-compose.yml` in `proxy/`
- **`lib/upstream.py`**: Generates service-specific `docker-compose.yml` files in `upstream/{project}/` directories
- **`api/main.py`**: FastAPI server providing REST API and GitHub webhook handlers for automated deployments
- **`bin/apply.py`**: Main orchestration script that regenerates all configs and updates deployments

### Directory Structure

```
/
├── db.yml                    # Single source of truth for all configuration
├── .env                      # Environment variables (API keys, domains, etc.)
├── lib/                      # Core Python modules
├── api/                      # FastAPI application
├── bin/                      # Utility scripts
├── tpl/                      # Jinja2 templates for docker-compose generation
├── proxy/                    # Generated Traefik proxy configuration
│   ├── docker-compose.yml    # Generated - do not edit manually
│   ├── docker-compose-dns.yml # DNS honeypot configuration
│   ├── traefik/              # Generated Traefik configs
│   └── tpl/                  # Traefik-specific Jinja2 templates
└── upstream/                 # Generated per-project deployments
    └── {project}/
        └── docker-compose.yml # Generated - do not edit manually
```

## CRITICAL RULES (ADHERE AT ALL COSTS!)

🚨 **NEVER DELETE ENTRIES FROM OPENSNITCH DATABASE** 🚨
- OpenSnitch database (`/var/lib/opensnitch/opensnitch.sqlite3`) is the **permanent security audit log**
- NEVER run DELETE queries against this database for ANY reason
- Historical block data is critical for security analysis and forensics
- False positives should be handled by:
  - Adding IPs to whitelist files (`data/whitelist/whitelist-outbound-ips.txt`)
  - Removing from blacklist files (`data/blacklist/blacklist-outbound-ips.txt`)
  - Clearing iptables rules
- OpenSnitch entries are **read-only** for analysis purposes
- If you need to "reset" threat detection, clear blacklist/whitelist files and iptables, NEVER touch OpenSnitch DB

## Common Development Commands

### Setup and Installation

```bash
bin/install.sh              # Create virtualenv and install dependencies
bin/start-all.sh            # Start proxy and API server
bin/apply.py                # Apply db.yml changes (regenerate configs + deploy)
bin/apply.py rollout        # Apply with zero-downtime rollout
```

### Testing and Validation

```bash
bin/test.sh                 # Run all Python unit tests (*_test.py files)
bin/lint.sh                 # Run linting
bin/format.sh               # Format code
bin/validate-db.py          # Validate db.yml schema
```

### Monitoring and Logs

```bash
bin/logs-api.sh             # Tail API server logs
```

### Utilities

```bash
bin/write-artifacts.py      # Regenerate proxy and upstream configs without deploying
bin/backup.py               # Backup upstream/ directory to S3
bin/requirements-update.sh  # Update Python dependencies
```

### Shell Utility Functions

Source `lib/functions.sh` to get helper functions:

```bash
source lib/functions.sh

dcp <cmd>                   # Run docker compose command in proxy/ (e.g., dcp logs -f)
dcu <project> <cmd>         # Run docker compose command for specific upstream project
dca <cmd>                   # Run docker compose command for all upstream projects
dcpx <service> <cmd>        # Execute command in proxy container
dcux <project> <svc> <cmd>  # Execute command in upstream service container
```

## Configuration Workflow

### Modifying Services

1. Edit `db.yml` to add/modify projects and services
2. Run `bin/validate-db.py` to check syntax
3. Run `bin/apply.py` to regenerate configs and deploy changes
4. For zero-downtime updates: `bin/apply.py rollout`

### Service Types in db.yml

**Managed Docker Services** (with `image` property):
- System generates `upstream/{project}/docker-compose.yml`
- Deployed and managed via Docker Compose
- Can use zero-downtime rollout with docker-rollout plugin

**External Services** (no `image` property):
- Services running elsewhere (host machine, other servers)
- Only proxy/ingress configuration generated
- Referenced by host IP or hostname

**Ingress Router Types**:
- `http`: Standard HTTP/HTTPS with TLS termination (default)
- `tcp`: TCP passthrough with TLS termination
- `udp`: UDP routing
- Use `passthrough: true` for TLS passthrough (no termination)

## API and Automation

### FastAPI Server

The API server (`api/main.py`) provides:

- **REST endpoints**: CRUD operations for projects/services (`/projects`, `/services`)
- **GitHub webhooks**: Automated deployments triggered by workflow completions
- **Authentication**: All endpoints require `API_KEY` via Bearer token, `X-API-KEY` header, or `apikey` query param

Key webhook endpoint:
```
POST /update-upstream/{project}?service={service}
```

Triggers deployment update for specified project/service.

### GitHub Webhook Integration

Configured to listen for `workflow_job` events. When a workflow completes successfully:
1. Webhook triggered with `?project={name}&service={name}`
2. If project is "itsUP": runs `git pull` and reapplies configuration (self-update)
3. Otherwise: pulls new image and performs rollout for the service

## Important Implementation Details

### Template Generation

All Docker Compose files are generated from Jinja2 templates in `tpl/` and `proxy/tpl/`:
- `tpl/docker-compose.yml.j2`: Template for upstream service deployments
- `proxy/tpl/docker-compose.yml.j2`: Template for proxy stack
- `proxy/tpl/routers-{http,tcp,udp}.yml.j2`: Templates for Traefik dynamic configuration

Templates have access to:
- `project`: Project object with all services
- Pydantic enum types (Protocol, Router, ProxyProtocol)
- Python builtins (isinstance, len, list, str)

### Zero-Downtime Rollout

Requires `docker rollout` plugin. Process:
1. Brings up new container and waits for health check (max 60s) or 10s if no health check
2. Kills old container and waits for drain
3. Removes old container

Only works for stateless services with proper health checks and SIGHUP handling.

### Data Model Validation

All configuration uses Pydantic models (`lib/models.py`):
- Automatic validation on db.yml changes
- Type safety for all configuration objects
- Custom validators (e.g., passthrough port 80 restrictions)

### Filtering Pattern

Many functions accept filter callbacks with variable arity:
```python
get_projects(filter=lambda p: p.enabled)                          # Filter by project
get_projects(filter=lambda p, s: s.image)                         # Filter by service
get_projects(filter=lambda p, s, i: i.router == Router.http)      # Filter by ingress
```

The system detects arity via `filter.__code__.co_argcount` and filters at the appropriate level.

## Testing

- Tests use Python's `unittest` framework
- Test files follow `*_test.py` naming convention
- Run all tests with `bin/test.sh`
- Key test files:
  - `lib/data_test.py`: Database operations
  - `lib/upstream_test.py`: Upstream generation
  - `bin/backup_test.py`: Backup functionality

## Plugin System

Plugins are configured in `db.yml` under `plugins:` section. Currently supported:

### CrowdSec

Web application firewall integration via Traefik plugin. Configuration includes:
- `enabled`: Enable/disable plugin
- `apikey`: Bouncer API key from CrowdSec container
- `version`: Plugin version
- `options`: Plugin-specific settings (log level, timeouts, CAPI credentials)

Plugins are instantiated using dynamic model loading in `lib/data.py:get_plugin_model()`.

## Environment Variables

Key variables in `.env`:

- `API_KEY`: Authentication for API endpoints
- `DOMAIN_SUFFIX`: Default domain suffix for services
- `TRAEFIK_DOMAIN`: Domain for Traefik dashboard
- `TRAEFIK_ADMIN`: Basic auth credentials for Traefik dashboard
- `LETSENCRYPT_EMAIL`: Email for Let's Encrypt certificates
- `LETSENCRYPT_STAGING`: Use staging environment (optional)
- `TRUSTED_IPS_CIDRS`: Comma-separated trusted IP ranges
- `AWS_*`: S3 credentials for backup functionality
- `BACKUP_EXCLUDE`: Comma-separated folders to exclude from backup

## Backup System

The `bin/backup.py` script:
- Creates tarball of `upstream/` directory
- Excludes folders specified in `BACKUP_EXCLUDE`
- Uploads to S3-compatible storage
- Maintains rolling window of 10 most recent backups
- Can be scheduled via cron for automated backups
