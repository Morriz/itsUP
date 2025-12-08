# itsUP <!-- omit in toc -->

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Linting: pylint](https://img.shields.io/badge/linting-pylint-yellowgreen)](https://github.com/pylint-dev/pylint)
[![Type checking: mypy](https://img.shields.io/badge/type%20checking-mypy-blue)](http://mypy-lang.org/)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL%203.0-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Tests: 87 passing](https://img.shields.io/badge/tests-87%20passing-brightgreen)](https://github.com/Morriz/itsUP)
[![Code quality: 9.96/10](https://img.shields.io/badge/code%20quality-9.96%2F10-brightgreen)](https://github.com/Morriz/itsUP)

_Lean, secure, automated, zero downtime<sup>\*</sup>, poor man's infra for services running in docker._

<img align="center" src="assets/freight-conductor.png">
<p></p>
<p>
Running a home network? Then you may already have a custom setup, probably using docker compose. You might enjoy all the maintenance and tinkering, but you are surely aware of the pitfalls and potential downtime. If you think that is ok, or if you don't want automation, then this stack is probably not for you.
Still interested? Then read on...
</p>

**Table of contents:**

- [Documentation](#documentation)
- [Key concepts](#key-concepts)
  - [Single source of truth](#single-source-of-truth)
  - [Managed proxy setup](#managed-proxy-setup)
  - [Managed service deployments \& updates](#managed-service-deployments--updates)
  - [\*Zero downtime?](#zero-downtime)
- [Apps included](#apps-included)
- [Prerequisites](#prerequisites)
- [Dev/ops tools](#devops-tools)
  - [itsup CLI](#itsup-cli)
  - [Utility scripts](#utility-scripts)
  - [Makefile](#makefile)
  - [DNS Honeypot](#dns-honeypot)
  - [Container Security Monitor](#container-security-monitor)
- [Howto](#howto)
  - [Install \& run](#install--run)
    - [1. Clone and setup repositories](#1-clone-and-setup-repositories)
    - [2. Run installation](#2-run-installation)
    - [3. Configure your installation](#3-configure-your-installation)
    - [4. Encrypt and commit secrets](#4-encrypt-and-commit-secrets)
    - [5. Deploy](#5-deploy)
    - [6. Monitor](#6-monitor)
  - [Configure services](#configure-services)
    - [Scenario 1: Adding an upstream service that will be deployed and managed](#scenario-1-adding-an-upstream-service-that-will-be-deployed-and-managed)
    - [Scenario 2: Adding a TLS passthrough endpoint](#scenario-2-adding-a-tls-passthrough-endpoint)
    - [Scenario 3: Adding a TCP endpoint](#scenario-3-adding-a-tcp-endpoint)
    - [Scenario 4: Adding a local (host) endpoint](#scenario-4-adding-a-local-host-endpoint)
    - [Project structure reference](#project-structure-reference)
  - [Configure plugins](#configure-plugins)
    - [CrowdSec](#crowdsec)
  - [Using the Api \& OpenApi spec](#using-the-api--openapi-spec)
  - [Webhooks](#webhooks)
  - [Backup and restore](#backup-and-restore)
    - [How the backup system works](#how-the-backup-system-works)
    - [Configure S3 backup settings](#configure-s3-backup-settings)
    - [Perform a manual backup](#perform-a-manual-backup)
    - [Set up scheduled backups](#set-up-scheduled-backups)
    - [Restore from a backup](#restore-from-a-backup)
  - [Threat Intelligence Reports](#threat-intelligence-reports)
    - [Configure AbuseIPDB API](#configure-abuseipdb-api)
    - [Generate threat report manually](#generate-threat-report-manually)
    - [Set up automated daily reports](#set-up-automated-daily-reports)
  - [OpenVPN server with SSH access](#openvpn-server-with-ssh-access)
    - [1. Initialize the configuration files and certificates](#1-initialize-the-configuration-files-and-certificates)
    - [2. Create a client file](#2-create-a-client-file)
    - [3. Retrieve the client configuration with embedded certificates and place in github workflow folder](#3-retrieve-the-client-configuration-with-embedded-certificates-and-place-in-github-workflow-folder)
    - [4. SSH access](#4-ssh-access)
    - [5. Make sure port 1194 is portforwarding the UDP protocol.](#5-make-sure-port-1194-is-portforwarding-the-udp-protocol)
- [Questions one might have](#questions-one-might-have)
  - [Why Traefik over Nginx?](#why-traefik-over-nginx)
  - [Does this scale to more machines?](#does-this-scale-to-more-machines)
- [Disclaimer](#disclaimer)

## Documentation

Comprehensive documentation is available in the `docs/` directory:

**Getting Started:**

- [Architecture Overview](docs/architecture.md) - System architecture and design principles
- [Networking](docs/networking.md) - Network topology and configuration

**Stacks:**

- [DNS Stack](docs/stacks/dns.md) - DNS honeypot management
- [Proxy Stack](docs/stacks/proxy.md) - Traefik configuration, routing, and TLS
- [API Stack](docs/stacks/api.md) - Management API architecture and deployment

**Operations:**

- [Logging](docs/operations/logging.md) - Log management and rotation
- [Monitoring](docs/operations/monitoring.md) - Container security monitoring
- [Backups](docs/operations/backups.md) - Backup and disaster recovery
- [Deployment](docs/operations/deployment.md) - Deployment procedures and best practices

**Development:**

- [Project Structure](docs/development/structure.md) - Codebase organization
- [Configuration](docs/development/configuration.md) - Configuration guide with schemas
- [Testing](docs/development/testing.md) - Testing strategies and practices

**Reference:**

- [CLI Reference](docs/reference/cli.md) - Complete command-line reference
- [Environment Variables](docs/reference/environment-variables.md) - All environment variables
- [Troubleshooting](docs/reference/troubleshooting.md) - Common issues and solutions

For a complete documentation index, see [docs/README.md](docs/README.md).

## Key concepts

### Single source of truth

The `projects/` directory is used for all the infra and workloads it creates and manages, to ensure a predictable and reliable automated workflow. Each project has its own `docker-compose.yml` and `ingress.yml` files, while infrastructure configuration lives in `projects/itsup.yml` and `projects/traefik.yml`.
This project-based structure provides both flexibility and reliability, and we strive to mirror standard docker compose functionality, which means no concessions are necessary from a docker compose enthusiast's perspective.

### Managed proxy setup

itsUP generates and manages `proxy/docker-compose.yml` which operates Traefik in a zero-downtime configuration:

**Architecture:**

- Traefik using Linux SO_REUSEPORT for zero-downtime updates (defaults to 1 replica)
- Host networking mode allows multiple instances to bind to same ports simultaneously
- Kernel load-balances incoming connections between scaled instances
- Users can scale manually: `docker compose up -d --scale traefik=N` (e.g., N=2 for high availability)
- Docker socket access secured via dockerproxy (wollomatic/socket-proxy) on localhost

**Capabilities:**

1. Terminate TLS and forward tcp/udp traffic over an encrypted network to listening endpoints
2. Passthrough TLS to endpoints (most people have secure Home Assistant setups already)
3. Open host ports if needed to choose a new port (openvpn service does exactly that)
4. Zero-downtime configuration updates via rolling deployment

### Managed service deployments & updates

itsUP generates and manages `upstream/{project}/docker-compose.yml` files to deploy container workloads based on your project configurations in `projects/{project}/`. Each project has a `docker-compose.yml` (service definitions) and `ingress.yml` (routing configuration).
This centralizes and abstracts away the plethora of custom docker compose setups that are mostly uniform in their approach anyway, so controlling their artifacts from a project-based structure makes a lot of sense.

### <sup>\*</sup>Zero downtime?

Like with all docker orchestration platforms (even Kubernetes) this is dependent on the containers:

- are healthchecks correctly implemented?
- Are SIGHUP signals respected to shutdown within an acceptable time frame?
- Are the containers stateless?

**Smart Change Detection:**

itsUP implements smart change detection that only performs rollouts when necessary:

- Compares Docker Compose config hashes (stored in container labels)
- Detects image updates, environment changes, volume changes, etc.
- Skips rollout if nothing changed (instant operation)
- Automatically performs zero-downtime rollout when changes detected

**Rollout Process:**

When changes are detected, itsUP will rollout via `docker rollout`:

1. Scale to double the current replicas (1→2, 2→4, etc. depending on your scale setting)
2. Wait for new containers to be healthy (max 60s with healthcheck, otherwise 10s)
3. Kill old containers and wait for drain
4. Remove old containers, leaving the same number of new replicas running

**Cost:** ~15 seconds when changes detected, instant when nothing changed.

_What about stateful services?_

It is surely possible to deploy stateful services but beware that those might not be good candidates for the `docker rollout` automation. In order to update those services it is strongly advised to first read the upgrade documentation for the newer version and follow the prescribed steps. More mature databases might have integrated these steps in the runtime, but expect that to be an exception. So, to garner correct results you are on your own and will have to read up on your chosen solutions.

## Apps included

See [itsup-projects](https://github.com/Morriz/itsUP-projects) for all the apps I am currently running.

## Prerequisites

**Tools:**

- [docker](https://www.docker.com) daemon and client
- docker [rollout](https://github.com/Wowu/docker-rollout) plugin
- [openvpn](https://openvpn.net): for testing vpn access (optional)

**Infra:**

- Portforwarding of port `80` and `443` to the machine running this stack. This stack MUST overtake whatever routing you now have, but don't worry, as it supports your home assistant setup and forwards any traffic it expects to it (configure your home-assistant project in `projects/home-assistant/`)
- A wildcard dns domain like `*.itsup.example.com` that points to your home ip. This allows to choose whatever subdomain for your services. You may of course choose and manage any domain in a similar fashion for a public service, but I suggest not going through such trouble for anything private.

## Dev/ops tools

### itsup CLI

The `itsup` CLI is the main interface for managing your infrastructure. It provides smart change detection and zero-downtime deployments:

**Main commands:**

```bash
# Initialization
itsup init                           # Initialize installation (clone repos, copy samples, setup git integration)

# Orchestrated Operations
itsup run                            # Run complete stack (orchestrated: dns→proxy→api→monitor in report-only mode)

# Stack-Specific Operations
# Every stack follows the same pattern: up, down, restart, logs [service]

itsup dns up                         # Start DNS stack
itsup dns down                       # Stop DNS stack
itsup dns restart                    # Restart DNS stack
itsup dns logs                       # Tail DNS stack logs

itsup proxy up                       # Start proxy stack
itsup proxy up traefik               # Start only Traefik
itsup proxy down                     # Stop proxy stack
itsup proxy restart                  # Restart proxy stack
itsup proxy logs                     # Tail all proxy logs
itsup proxy logs traefik             # Tail Traefik logs only

# Configuration & Deployment
itsup apply [project]                # Apply configurations with smart zero-downtime updates
itsup validate [project]             # Validate project configurations
itsup migrate                        # Migrate configuration schema to latest version

# Project Service Management
itsup svc <project> <cmd> [service]  # Docker compose operations for project services
itsup svc <project> up               # Start all services in a project
itsup svc <project> logs -f          # Tail project logs
itsup svc <project> exec web sh      # Execute commands in containers

# Container Security Monitor
itsup monitor start [--flags]        # Start security monitor
itsup monitor stop                   # Stop monitor
itsup monitor logs                   # Tail monitor logs
itsup monitor cleanup                # Review blacklist
itsup monitor report                 # Generate threat report

# Options
itsup --version                      # Show version
itsup -v                             # Enable DEBUG logging
itsup -vv                            # Enable TRACE logging (very verbose)
```

**Schema Versioning & Migrations:**

itsUP tracks configuration schema versions to ensure compatibility between the CLI and your configuration files. When you upgrade itsUP to a newer version that includes schema changes, you'll need to run a migration:

```bash
# Check if migration is needed (automatic on most commands)
itsup validate                       # Will warn if schema is outdated

# Dry-run to see what would change
itsup migrate --dry-run              # Preview changes without applying

# List pending migrations
itsup migrate --list                 # Show which fixers would run

# Run migration
itsup migrate                        # Upgrade configuration schema
```

**Migration Features:**

- Idempotent fixers (safe to run multiple times)
- Git-aware file operations (uses `git mv` to preserve history)
- Automatic validation after migration
- Version tracked in `projects/itsup.yml` (`schemaVersion` field)

**Smart Output:**

itsUP automatically adapts its output based on context:

- **Interactive terminal (TTY)**: Clean colored output with symbols

  ```
  ✓ Migration complete!
  ⚠ Config needs review
  ✗ Failed to rename project
  ```

- **Pipes/logs/automation**: Full structured output with timestamps
  ```
  2025-11-04 00:11:48.166 INFO lib/migrations.py:97 Migration complete!
  2025-11-04 00:11:48.166 WARNING lib/migrations.py:71 Config needs review
  2025-11-04 00:11:48.166 ERROR lib/fixers/rename_ingress.py:62 Failed to rename project
  ```

**Smart Behavior:**

- `apply` command uses config hash comparison - only performs rollouts when changes detected
- Tab completion for project names, docker compose commands, and service names
- All commands work from project root (no need to cd into directories)
- Zero-downtime rollouts only happen when actual changes detected

**Directory → Command Mapping:**

- `dns/docker-compose.yml` → `itsup dns`
- `proxy/docker-compose.yml` → `itsup proxy`
- `upstream/project/` → `itsup svc project`

**Orchestrated vs Stack Operations:**

- `itsup run` = Full orchestrated startup (dns→proxy→api→monitor in report-only mode) in correct dependency order
- `itsup dns up` = Stack-specific operation (just DNS)
- `itsup proxy up` = Stack-specific operation (just proxy)
- Different semantics: `run` does everything, stack commands are surgical

**Note**: `itsup run` starts the monitor in report-only mode (detection without blocking). For full protection with blocking, use `itsup monitor start`.

### Utility scripts

- `bin/write_artifacts.py`: after updating project configurations in `projects/` you can run this script to generate new artifacts (or use `itsup apply` which does this automatically).
- `bin/requirements-update.sh`: You may want to update requirements once in a while ;)

### Makefile

A minimal Makefile focused on development workflow. Run `make help` to see all available targets:

```bash
make install           # Install deps + install/enable itsup-bringup systemd service
make test              # Run all tests
make lint              # Run linter
make format            # Format code
make clean             # Remove generated artifacts
```

**For runtime operations** (run/dns/proxy/svc/monitor), use `itsup` commands instead. The Makefile is intentionally minimal to avoid command sprawl.

**Background automation**
- `itsup-bringup.service` (enabled): runs `itsup run && itsup apply` at boot; `itsup down --clean` on shutdown.
- `itsup-apply.timer` (enabled): runs `itsup apply` nightly at 03:00 (systemd timer).
- `itsup-backup.timer` (enabled): runs `bin/backup.py` nightly at 05:00 (systemd timer).
- `pi-healthcheck.timer` (enabled): runs `bin/pi-healthcheck.sh` every 5 minutes (systemd timer) with maintenance window logic (02:30–03:30 aggressive, otherwise strike-based).

### DNS Honeypot

All container DNS traffic is routed through a DNS honeypot (`dns-honeypot` container) that logs all queries and responses. This is essential for the container security monitoring system.

The DNS honeypot is managed via `proxy/docker-compose-dns.yml` and runs dnsmasq with query logging enabled. It integrates with the proxy network to intercept all container DNS requests.

### Container Security Monitor

Real-time container security monitoring that detects compromised containers by identifying hardcoded IP connections through DNS correlation analysis.

**Key Features:**

- DNS correlation detection (connections without DNS = malware)
- Real-time Docker events integration
- OpenSnitch cross-reference (optional)
- iptables blocking (optional)
- Automatic IP list management with hot-reload
- Historical analysis with timestamp resumption

**Quick Start:**

```bash
# Start monitor with full protection (blocking enabled)
itsup monitor start --use-opensnitch

# Detection only (no blocking) - also started automatically by "itsup run"
itsup monitor start --report-only --use-opensnitch

# Stop monitor
itsup monitor stop

# View logs
itsup monitor logs

# Generate threat intelligence report
itsup monitor report
```

**Note**: `itsup run` automatically starts the monitor in report-only mode for safe operation during infrastructure startup. To enable active blocking, explicitly run `itsup monitor start`.

**📖 For complete documentation, see [monitor/README.md](monitor/README.md)**

This includes:

- Architecture and detection logic
- Configuration options
- False positive handling
- Testing guide
- Performance characteristics

## Howto

### Install & run

#### 1. Clone and setup repositories

itsUP uses separate git repositories for configuration and secrets management:

**Create the repositories:**

```bash
# Create a private repository for your project configurations
# (on GitHub, GitLab, or your preferred git host)
# Name it something like: itsup-projects

# Create a private repository for your secrets
# Name it something like: itsup-secrets
```

**Clone itsUP:**

```bash
git clone https://github.com/Morriz/itsUP.git
cd itsUP
```

**Why separate repositories?**

- `projects/`: Contains your service configurations (YAML files). This keeps your infrastructure-as-code separate from the itsUP codebase, allowing you to manage and version your configurations independently.
- `secrets/`: Contains encrypted secrets (using SOPS). Keeping secrets in a separate repository improves security and access control.

Both repositories are **gitignored** in the main itsUP repo and managed as independent git repositories.

#### 2. Run installation

Install everything + systemd bringup service:

```bash
make install
```

This installs dependencies and installs/enables the `itsup-bringup` systemd service, which runs `itsup run && itsup apply` at boot and `itsup down --clean` at shutdown.

If you prefer to run only the CLI bootstrap, the `itsup init` command will:

- Prompt for git URLs and clone `projects/` and `secrets/` repositories
- Copy sample configuration files (won't overwrite existing files)
- Set up Python virtual environment
- Install dependencies

```bash
itsup init
```

The script will copy sample files to:

- `.env` (environment variables)
- `projects/traefik.yml` (base Traefik configuration)
- `secrets/itsup.txt` (template for required secrets)

#### 3. Configure your installation

Edit the copied files:

1. **`.env`**: Configure environment variables as needed
2. **`projects/traefik.yml`**: Change `domain_suffix` to your domain
3. **`secrets/itsup.txt`**: Fill in ALL required secrets (validation will fail if any are empty)

#### 4. Encrypt and commit secrets

```bash
# Encrypt secrets with SOPS
cd secrets
sops -e itsup.txt > itsup.enc.txt

# Commit to your secrets repository
git add itsup.enc.txt
git commit -m "Initial secrets"
git push

# Commit your project configuration
cd ../projects
git add traefik.yml
git commit -m "Initial configuration"
git push
```

#### 5. Deploy

```bash
# Apply your configuration with zero-downtime updates
itsup apply
```

#### 6. Monitor

```bash
# Tail all logs
bin/tail-logs.sh

# Or use make
make logs
```

### Configure services

Project and service configuration uses a project-based structure in the `projects/` directory. Each project has its own subdirectory with `docker-compose.yml` and `ingress.yml` files.

#### Scenario 1: Adding an upstream service that will be deployed and managed

Create a new directory in `projects/` with two files:

**projects/whoami/docker-compose.yml:**

```yaml
services:
  web:
    image: traefik/whoami:latest
    restart: unless-stopped
    networks:
      - proxynet

networks:
  proxynet:
    external: true
```

**projects/whoami/ingress.yml:**

```yaml
enabled: true
ingress:
  - service: web
    domain: whoami.example.com
    port: 80
    router: http
```

Run `itsup apply whoami` to generate artifacts and deploy the service.

#### Scenario 2: Adding a TLS passthrough endpoint

Create a project with `passthrough: true` in the ingress configuration.

**projects/home-assistant/ingress.yml:**

```yaml
enabled: true
ingress:
  - service: hass
    domain: home.example.com
    port: 443
    router: http
    passthrough: true
```

**projects/home-assistant/docker-compose.yml:**

```yaml
services:
  hass:
    image: homeassistant/home-assistant:latest
    restart: unless-stopped
    networks:
      - proxynet
    ports:
      - '8123:8123'

networks:
  proxynet:
    external: true
```

If you also need port 80 for HTTP challenges, add another ingress entry:

```yaml
ingress:
  - service: hass
    domain: home.example.com
    port: 443
    router: http
    passthrough: true
  - service: hass
    domain: home.example.com
    port: 80
    router: http
    path_prefix: /.well-known/acme-challenge/
```

(Port 80 is only allowed for ACME challenges with passthrough.)

#### Scenario 3: Adding a TCP endpoint

Use `router: tcp` in the ingress configuration.

**projects/minio/docker-compose.yml:**

```yaml
services:
  app:
    image: minio/minio:latest
    command: server --console-address ":9001" /data
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
    volumes:
      - /data/minio:/data
    restart: unless-stopped
    networks:
      - proxynet

networks:
  proxynet:
    external: true
```

**projects/minio/ingress.yml:**

```yaml
enabled: true
ingress:
  - service: app
    domain: minio-api.example.com
    port: 9000
    router: tcp
  - service: app
    domain: minio-ui.example.com
    port: 9001
    router: http
```

**projects/minio/secrets.txt:** (optional project-specific secrets)

```
MINIO_ROOT_USER=admin
MINIO_ROOT_PASSWORD=secret123
```

#### Scenario 4: Adding a local (host) endpoint

For services running on the host (not in Docker), create a minimal ingress-only configuration.

**projects/itsup/ingress.yml:**

```yaml
enabled: true
ingress:
  - service: api
    domain: itsup.example.com
    port: 8888
    router: http
    target: 172.17.0.1 # Docker bridge IP (use host.docker.internal on Docker Desktop)
```

**projects/itsup/docker-compose.yml:**

```yaml
# Empty or minimal - no containers needed for host services
services: {}
```

#### Project structure reference

Each project directory follows this pattern:

```
projects/
└── {project-name}/
    ├── docker-compose.yml   # Standard Docker Compose file
    ├── ingress.yml          # Routing configuration (IngressV2 schema)
    └── secrets.txt          # (Optional) Project-specific secrets
```

**IngressV2 schema:**

```yaml
enabled: true # Enable/disable routing for this project
ingress:
  - service: web # Service name from docker-compose.yml
    domain: example.com # Domain for routing
    port: 80 # Container port
    router: http # Router type: http, tcp, udp
    passthrough: false # (Optional) TLS passthrough
    path_prefix: / # (Optional) Path-based routing
    hostport: 8080 # (Optional) Expose on host port
```

See `samples/example-project/` for a complete working example.

### Configure plugins

You can enable and configure plugins in `projects/traefik.yml`. Right now we support the following:

#### CrowdSec

[CrowdSec](https://www.crowdsec.net) can run as a container via plugin [crowdsec-bouncer-traefik-plugin](https://github.com/maxlerebourg/crowdsec-bouncer-traefik-plugin).

**Step 1: generate api key**

First set `enable: true`, run `bin/write_artifacts.py`, and bring up the `crowdsec` container:

```bash
itsup svc traefik up crowdsec
```

Now we can execute the command to get the key:

```bash
itsup svc traefik exec crowdsec cscli bouncers add crowdsecBouncer
```

Put the resulting api key in `secrets/itsup.txt` as `CROWDSEC_API_KEY=<your-key>`, then reference it in `projects/traefik.yml` configuration and apply with `itsup apply`.
Crowdsec is now running and wired up, but does not use any blocklists yet. Those can be managed manually, but preferable is to become part of the community by creating an account with CrowdSec to get access and contribute to the community blocklists, as well as view results in your account's dashboards.

**Step 2: connect your instance with the CrowdSec console**

After creating an account create a machine instance in the console, and register the enrollment key in your stack:

```bash
itsup svc traefik exec crowdsec cscli console enroll ${enrollment key}
```

**Step 3: subscribe to 3rd party blocklists**

In the [security-engines](https://app.crowdsec.net/security-engines) section select the "Blocklists" of your engine and choose some blocklists of interest.
Example:

- Free proxies list
- Firehol SSL proxies list
- Firehol cruzit.com list

**Step 4: add ip (or cidr) to whitelist**

```bash
itsup svc traefik exec crowdsec cscli allowlists create me -d "my dev ips"
itsup svc traefik exec crowdsec cscli allowlists add me 123.123.123.0/24
```

### Using the Api & OpenApi spec

The API allows openapi compatible clients to do management on this stack (ChatGPT works wonders).

Generate the spec with `api/extract-openapi.py`.

All endpoints do auth and expect either:

- an incoming Bearer token
- `X-API-KEY` header
- `apikey` query param

to be set to `.env/API_KEY`.

Exception: Only github webhook endpoints (check for annotation `@app.hooks.register(...`) get it from the `github_secret` header.

### Webhooks

Webhooks are used for the following:

1. to receive updates to this repo, which will result in a `git pull` and `bin/apply.py` to update any changes in the code. The provided project with `name: itsUP` is used for that, so DON'T delete it if you care about automated updates to this repo.
2. to receive incoming github webhooks (or GET requests to `/update-upstream?project=bla&service=dida`) that result in rolling up of a project or specific service only.

One GitHub webhook listening to `workflow_job`s is provided, which needs:

- the hook you will register in the github project to end with `/hook?project=bla&service=dida` (`service` optional), and the `github_secret` set to `.env/API_KEY`.

I mainly use GitHub workflows and created webhooks for my individual projects, so I can just manage all webhooks in one place.

**NOTE:**

When using crowdsec this webhook is probably not coming in as it exits the Azure cloud (public IP range), which is also host to many malicious actors that spin up ephemeral intrusion tools. To still receive signals from github you can use a vpn setup as the one used in this repo (check `.github/workflows/test.yml`).

### Backup and restore

itsUP includes a robust backup system that archives your service configurations and uploads them to S3-compatible storage for safekeeping. The backup functionality is implemented in `bin/backup.py`.

#### How the backup system works

The backup system:

1. Creates a tarball (`itsup.tar.gz`) of your `upstream` directory, which contains all your service configurations
2. Excludes any folders specified in the `BACKUP_EXCLUDE` environment variable
3. Uploads the tarball to an S3-compatible storage service
4. Implements backup rotation, keeping only the 10 most recent backups
5. Automatically adds timestamps to backup filenames for versioning

#### Configure S3 backup settings

To use the backup functionality, you need to configure the following environment variables in your `.env` file:

```

AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_S3_HOST=your_s3_host
AWS_S3_REGION=your_s3_region
AWS_S3_BUCKET=your_bucket_name
BACKUP_EXCLUDE=folder1,folder2 # Optional: comma-separated list of folders to exclude from backup

```

#### Perform a manual backup

To manually run a backup:

```sh
sudo .venv/bin/python bin/backup.py
```

#### Set up scheduled backups

For automated backups, you can set up a cron job. For example, to run a backup daily at 2 AM:

```
0 5 * * * cd /path/to/itsup && .venv/bin/python bin/backup.py
```

#### Restore from a backup

To restore from a backup, you'll need to:

1. Download the desired backup from your S3 bucket
2. Extract the tarball to restore your configurations:

```sh
tar -xzf itsup.tar.gz.{timestamp} -C /path/to/itsup/
```

3. Run the following to apply the restored configurations (assuming itsup installed and activated with `source env.sh`):

```sh
itsup run # to start the proxy stack
itsup apply # to deploy restored services
```

### Threat Intelligence Reports

itsUP includes automated threat analysis that correlates blacklisted IPs with threat intelligence from AbuseIPDB, performing reverse DNS lookups and WHOIS queries to identify potential threat actors.

#### Configure AbuseIPDB API

To enable threat intelligence lookups, add your AbuseIPDB API key to `.env`:

```
ABUSEIPDB_API_KEY=your_api_key_here
```

Get a free API key at https://www.abuseipdb.com/register (1,000 checks/day on free tier).

#### Generate threat report manually

```bash
make monitor-report
```

This generates `reports/potential_threat_actors.csv` with:

- Network ranges and abuse confidence scores
- Organization details and contact information
- Usage type (Datacenter, Hosting, ISP, etc.)
- Tor exit node detection
- Last reported timestamp

The script is incremental - it only analyzes NEW IPs not already in the report.

#### Set up automated daily reports

Add to root's crontab to run daily at 4 AM:

```bash
sudo crontab -e
```

Add this line:

```
0 4 * * * cd /path/to/itsup && make monitor-report >> /var/log/threat_analysis.log 2>&1
```

### OpenVPN server with SSH access

This setup contains a project called "vpn" which runs an openvpn service that gives ssh access. To bootstrap it:

#### 1. Initialize the configuration files and certificates

```bash
itsup svc vpn run vpn-openvpn ovpn_genconfig -u udp4://vpn.itsup.example.com
itsup svc vpn run vpn-openvpn ovpn_initpki
```

Save the signing passphrase you created.

#### 2. Create a client file

```bash
export CLIENTNAME='github'
itsup svc vpn run vpn-openvpn easyrsa build-client-full $CLIENTNAME
```

Save the client passphrase you created as it will be used for `OVPN_PASSWORD` below.

#### 3. Retrieve the client configuration with embedded certificates and place in github workflow folder

```bash
itsup svc vpn run vpn-openvpn ovpn_getclient $CLIENTNAME combined > .github/workflows/client.ovpn
```

**IMPORTANT:** Now change `udp` to `udp4` in the `remote: ...` line to target UDP with IPv4 as docker is still not there.

Test access (expects local `openvpn` installed):

```
sudo openvpn .github/workflows/client.ovpn
```

Now save the `$OVPN_USER_KEY` from `client.ovpn`'s `<key>$OVPN_USER_KEY</key>` and remove the `<key>...</key>`.
Also save the `$OVPN_TLS_AUTH_KEY` from `<tls-auth...` section and remove it.

Add the secrets to your github repo

- `OVPN_USERNAME`: `github`
- `OVPN_PASSWORD`: the client passphrase
- `OVPN_USER_KEY`
- `OVPN_TLS_AUTH_KEY`

#### 4. SSH access

In order for ssh access by github, create a private key and add the pub part to the `authorized_keys` on the host:

```

ssh-keygen -t ed25519 -C "your_email@example.com"
cat ~/.ssh/id_ed25519.pub >> ~/.ssh/authorized_keys

```

Add the secrets to GitHub:

- `SERVER_HOST`: the hostname of this repo's api server
- `SERVER_USERNAME`: the username that has access to your host's ssh server
- `SSH_PRIVATE_KEY`: the private key of the user

#### 5. Make sure port 1194 is portforwarding the UDP protocol.

Now we can start the server and expect all to work ok.

If you wish to revoke a cert or do something else, please visit this page: [kylemanna/docker-openvpn/blob/master/docs/docker-compose.md](https://github.com/kylemanna/docker-openvpn/blob/master/docs/docker-compose.md)

## Questions one might have

### Why Traefik over Nginx?

Traefik was chosen for several key reasons:

- **Dynamic configuration**: Automatically picks up container changes via Docker labels
- **Automatic cert management**: Manages Let's Encrypt certificates gracefully with built-in ACME support
- **Zero-downtime updates**: With SO_REUSEPORT, can run multiple instances on same ports
- **Kubernetes-like labels**: Familiar L7 routing configuration for those from K8s background
- **No manual cert rotation**: Unlike Nginx which requires cron jobs for certificate renewal

While Nginx can be faster in raw performance (~40%), Traefik's automation and zero-downtime capabilities make it the better choice for this use case.

### Does this scale to more machines?

In the future we might consider expanding this setup to use docker swarm, as it should be easy to do. For now we like to keep it simple.

## Disclaimer

**Don't blame this infra automation tooling for anything going wrong inside your containers!**

I suggest you repeat that mantra now and then and question yourself when things go wrong: where lies the problem?
