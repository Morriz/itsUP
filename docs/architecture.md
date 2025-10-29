# Architecture Overview

itsUP is a zero-downtime infrastructure management system built around Docker Compose, Traefik, and Python automation.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Internet                            │
└────────────────────┬────────────────────────────────────────┘
                     │
              ┌──────▼──────┐
              │   Router    │  Port forwards 80/443/8080/8443
              │ 192.168.1.1 │
              └──────┬──────┘
                     │
              ┌──────▼──────────┐
              │   itsUP Host    │
              │  (Raspberry Pi) │
              └─────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
   ┌────▼───┐  ┌────▼────┐  ┌────▼─────┐
   │  DNS   │  │  Proxy  │  │ Upstream │
   │ Stack  │  │  Stack  │  │ Projects │
   └────────┘  └─────────┘  └──────────┘
```

## Core Components

### 1. DNS Stack
- **Purpose**: DNS honeypot for security monitoring
- **Network**: Creates `proxynet` bridge network (172.20.0.0/16)
- **Services**: DNS honeypot (port 53)
- **Started first**: Other stacks depend on `proxynet`

### 2. Proxy Stack
- **Purpose**: Reverse proxy, TLS termination, routing
- **Network**: Host network mode (for zero-downtime scaling)
- **Services**:
  - Traefik (v3.5.1) - Reverse proxy
  - dockerproxy - Secure Docker API access
  - CrowdSec - Threat detection and banning

### 3. API Server
- **Purpose**: Infrastructure management REST API
- **Type**: Non-containerized Python FastAPI app
- **Port**: 8888 (internal)
- **Routing**: Exposed via Traefik at `itsup.srv.instrukt.ai`

### 4. Security Monitor
- **Purpose**: Container network security monitoring
- **Type**: Non-containerized Python service
- **Integration**: OpenSnitch, iptables, threat intelligence

### 5. Upstream Projects
- **Purpose**: User workloads (apps, databases, services)
- **Network**: `proxynet` (connected to proxy)
- **Deployment**: Parallel zero-downtime rollouts
- **Discovery**: Auto-discovered by Traefik via Docker labels

## Data Flow

### HTTP/HTTPS Request Flow

```
Internet Request (example.com)
    │
    ▼
Router (NAT/Port Forward)
    │
    ▼
Traefik (Host Network :80/:443)
    │
    ├─ TLS Termination
    ├─ CrowdSec Check (block if malicious)
    ├─ Router Match (Host/Path rules)
    │
    ▼
Upstream Service (proxynet)
    │
    ▼
Response back through Traefik
```

### Configuration Flow

```
User runs: itsup apply
    │
    ▼
Read projects/{project}/ingress.yml
    │
    ▼
Generate Traefik labels
    │
    ▼
Write upstream/{project}/docker-compose.yml
    │
    ▼
Smart rollout (scale up → health check → scale down old)
    │
    ▼
Traefik auto-discovers new containers
```

## Network Architecture

### Networks

1. **Host Network** (Traefik)
   - Direct access to host ports
   - Zero-downtime scaling (multiple Traefik instances)
   - No NAT overhead

2. **proxynet Bridge** (172.20.0.0/16)
   - Connects all upstream services
   - DNS resolution between containers
   - Isolated from external access (except via Traefik)

3. **Project Networks** (optional)
   - Internal communication (e.g., app ↔ database)
   - Isolated from other projects

### Port Mapping

**External (Router → Host):**
- 80 → Host :80 (HTTP)
- 443 → Host :443 (HTTPS)
- 8080 → Host :8080 (Traefik HTTP internal)
- 8443 → Host :8443 (Traefik HTTPS internal)

**Internal (Host):**
- :8888 - API server
- :2375 - dockerproxy (Docker API)
- :8080, :8443 - Traefik entrypoints
- :18080 - CrowdSec API

## Deployment Model

### Zero-Downtime Deployments

When `itsup apply` runs:

1. **Hash Check**: Compare config hash with running container
2. **Skip if unchanged**: No rollout needed
3. **If changed**:
   - Scale up new container (e.g., `app-2`)
   - Wait for health check to pass
   - Scale down old container (e.g., `app-1`)
   - No traffic interruption

### Parallel Deployments

Multiple projects deploy simultaneously:
- Each project rolled out independently
- Shared progress tracking
- Early termination on failure

## File Structure

```
/home/morriz/srv/
├── api/                    # API server code
├── bin/                    # CLI scripts and utilities
├── commands/               # itsup subcommands
├── crowdsec/               # CrowdSec config
├── data/                   # Persistent data (acme, crowdsec)
├── dns/                    # DNS stack compose file
├── docs/                   # Documentation (this)
├── lib/                    # Shared Python libraries
├── logs/                   # File-based logs
├── monitor/                # Security monitor code
├── proxy/                  # Proxy stack (Traefik config)
├── projects/               # User project configs
│   ├── itsup.yml          # Infrastructure config
│   ├── traefik.yml        # Traefik overrides
│   └── {project}/         # Per-project configs
│       ├── docker-compose.yml
│       └── ingress.yml
├── secrets/                # Encrypted secrets (SOPS)
├── tpl/                    # Jinja2 templates
└── upstream/               # Generated compose files (deployed)
    ├── {project}/
    │   └── docker-compose.yml  # Generated + deployed
    └── ...
```

## Security Architecture

### Defense in Depth

1. **Network Level**:
   - DNS honeypot detects malicious DNS queries
   - OpenSnitch monitors all container network traffic
   - iptables blocks unauthorized connections

2. **Application Level**:
   - CrowdSec analyzes HTTP traffic for attacks
   - Traefik enforces TLS, rate limiting
   - Security headers (HSTS, CSP, etc.)

3. **Container Level**:
   - Read-only containers where possible
   - No privileged containers
   - Minimal capabilities

4. **Data Level**:
   - Secrets encrypted with SOPS
   - TLS certificates managed by Let's Encrypt
   - Backups encrypted in S3

### Threat Detection Flow

```
Malicious Request
    │
    ▼
CrowdSec (log analysis)
    │
    ├─ Detects pattern (SQL injection, brute force, etc.)
    ├─ Creates ban decision
    │
    ▼
Traefik Bouncer Plugin
    │
    ├─ Fetches ban list from CrowdSec
    ├─ Blocks banned IPs
    │
    ▼
Request rejected (403 Forbidden)
```

## Technology Stack

### Core Infrastructure
- **Docker** + **Docker Compose** - Containerization and orchestration
- **Traefik v3** - Reverse proxy, load balancer, TLS
- **CrowdSec** - Collaborative threat detection
- **OpenSnitch** - Application firewall

### Management Layer
- **Python 3.11** - CLI, API, monitor
- **FastAPI** - REST API framework
- **Click** - CLI framework
- **Jinja2** - Template engine
- **SOPS** - Secrets encryption

### Monitoring & Logging
- **Docker logging** - Container stdout/stderr
- **File-based logs** - Traefik access, API, monitor
- **logrotate** - Log rotation and compression

## Design Principles

1. **Zero Downtime** - All operations maintain service availability
2. **Declarative Configuration** - Infrastructure as code
3. **Security First** - Multiple layers of defense
4. **Automation** - Minimal manual intervention
5. **Observability** - Comprehensive logging and monitoring
6. **Simplicity** - Avoid over-engineering
7. **Idempotency** - Operations can be safely repeated

## Scalability

Current deployment is single-host (Raspberry Pi), but architecture supports:

- **Horizontal scaling**: Multiple Traefik instances (host network mode)
- **Service scaling**: `docker compose up --scale app=3`
- **Multi-host**: Potential for Docker Swarm or Kubernetes migration
- **Load distribution**: Traefik built-in load balancing

## State Management

### Stateless
- Traefik (config from labels)
- API server (reads from filesystem)
- Upstream services (mostly stateless)

### Stateful
- Databases (PostgreSQL, MySQL) - Volume mounts
- Let's Encrypt certificates - `data/acme/`
- CrowdSec decisions - `data/crowdsec/`
- Project data - `upstream/{project}/data/`

## Related Documentation

- [Networking Details](networking.md)
- [DNS Stack](stacks/dns.md)
- [Proxy Stack](stacks/proxy.md)
- [Deployment Process](operations/deployment.md)
