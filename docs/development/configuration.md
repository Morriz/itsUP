# Configuration Guide

Comprehensive guide to configuring itsup infrastructure and projects.

## Configuration Files Overview

### Infrastructure Configuration

**`projects/itsup.yml`**:
```yaml
schemaVersion: "2.1.0"

# Traefik dashboard domain (REQUIRED — consumed by write_dynamic_routers)
traefikDomain: traefik.example.com

# Router IP — set explicitly, or leave blank for netifaces auto-detection
# (auto-detected value is written back here on first run)
routerIP: 192.168.1.1

# Backup configuration (s3 values come from secrets as ${VAR})
backup:
  exclude: []            # project names to exclude from backup
  s3:
    host: ${AWS_S3_HOST}
    region: ${AWS_S3_REGION}
    bucket: ${AWS_S3_BUCKET}

# CrowdSec bouncer (read by write_middleware_config)
crowdsec:
  enabled: true
  apikey: '${CROWDSEC_APIKEY}'
  collections:
    - crowdsecurity/traefik

# Component version pinning (consumed by the proxy compose template)
versions:
  traefik: v3.5.4
  crowdsec: v1.7.3
```

**Purpose**:
- Global infrastructure settings
- Shared across all projects
- Secrets as `${VAR}` placeholders (left unexpanded; resolved at runtime)

**Note**: The actual keys read by the code are `schemaVersion`, `traefikDomain`, `routerIP`, `backup`, `crowdsec`, and `versions`. There is no `router_ip` (snake_case), `monitoring`, `dns`, `include_volumes`, or `compression` key.

### Traefik Overrides

**`projects/traefik.yml`**:
```yaml
# Custom middlewares
http:
  middlewares:
    rate-limit:
      rateLimit:
        average: 100
        burst: 50

# Custom entrypoints
entryPoints:
  custom-port:
    address: ":9000"

# Logging overrides
log:
  level: INFO  # Override default DEBUG
```

**Purpose**:
- User customizations for Traefik
- Merged on top of generated base config
- Full Traefik v3 configuration schema supported

### Project Configuration

**`projects/{project}/docker-compose.yml`**:
```yaml
services:
  web:
    image: nginx:latest
    environment:
      - NGINX_HOST=${DOMAIN}        # From secrets/
      - NGINX_PORT=80
    volumes:
      - ./html:/usr/share/nginx/html:ro
    networks:
      - traefik
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost/health"]
      interval: 30s
      timeout: 5s
      retries: 3

networks:
  traefik:
    external: true
```

**Purpose**:
- Standard Docker Compose file
- Service definitions (images, volumes, networks)
- Secrets as `${VAR}` placeholders

**Note on networks**: The sample uses an external `traefik` network. The generator (`write_upstream`) auto-injects the `proxynet` external network onto any service that has an ingress rule, so projects do not strictly need to declare `proxynet` themselves — services with ingress are attached to it during artifact generation.

**`projects/{project}/itsup-project.yml`**:
```yaml
enabled: true
ingress:
  - service: web
    domain: example.com
    port: 80
    router: http
```

**Purpose**:
- Routing configuration (parsed into `TraefikConfig`/`Ingress` in `lib/models.py`)
- Auto-generates Traefik labels
- Simpler than manual label management
- Legacy name `ingress.yml` is still read with a deprecation warning (support ends in v3.0); rename to `itsup-project.yml`.

### Secrets Configuration

**`secrets/itsup.txt`** (shared):
```bash
ROUTER_IP=192.168.1.1
API_SECRET_KEY=supersecret
BACKUP_S3_KEY=...
BACKUP_S3_SECRET=...
```

**`secrets/{project}.txt`** (project-specific):
```bash
DOMAIN=example.com
DB_PASSWORD=secretpass
API_KEY=abc123
```

**Purpose**:
- Environment variables for deployment
- **Mutually exclusive contexts** (not merged): infrastructure deploys load ONLY `secrets/itsup.{enc.txt|txt}`; a project deploy loads ONLY `secrets/{project}.{enc.txt|txt}`. A project does NOT inherit `itsup.txt`. Per file, the encrypted `.enc.txt` is tried first, then plaintext `.txt`.
- Encrypted with SOPS for git storage

## Configuration Schema Reference

### Ingress Schema (itsup-project.yml)

The file is parsed into `TraefikConfig`, whose `ingress` list holds `Ingress` rows (`lib/models.py`). Project-level keys:

```yaml
enabled: boolean                    # default true. false => apply STOPS the project's containers
host: string | null                 # External host IP/hostname (ingress-only projects, no containers)
ingress: [Ingress]                  # list of ingress rows (see below)
egress: [string]                    # "project:service" targets this project may reach
```

Each `Ingress` row (real fields — there is no `middleware` field, and `passthrough` is top-level, not under `tls`):

```yaml
- service: string | null            # service name in docker-compose.yml (container projects)
  domain: string | null             # public domain; TLS terminated for this domain. Omit => not publicly exposed
  port: integer                     # service port (default 8080)
  hostport: integer | null          # host port to expose (drives TCP/UDP entrypoint generation)
  router: "http" | "tcp" | "udp"    # router type (default http)
  protocol: "tcp" | "udp"           # port protocol (default tcp)
  passthrough: boolean              # forward traffic without terminating TLS (default false)
  proxyprotocol: 1 | 2 | null       # PROXY protocol version the service expects (default 2; null disables)
  path_prefix: string | null        # expose under a path prefix (adds PathPrefix to the rule)
  path_remove: boolean              # strip the path prefix before forwarding (default false)
  expose: boolean                   # expose to other internal services (default false)
  ipv4_address: string | null       # pin a static IP on proxynet (must be within 172.20.0.0/16)
  dns: [string] | null              # explicit dns: block for the service (replaces default honeypot injection)
  tls:                              # alternative to `domain`: a main + SANs cert
    main: string
    sans: [string]
```

#### HTTP Router Example

```yaml
enabled: true
ingress:
  - service: web
    domain: my-app.example.com
    port: 3000
    router: http
```

**Generates** (router name is suffixed with the port: `{project}-{service}-{port}`):
```yaml
labels:
  - traefik.enable=true
  - traefik.http.routers.project-web-3000.entrypoints=web-secure
  - traefik.http.routers.project-web-3000.rule=Host(`my-app.example.com`)
  - traefik.http.routers.project-web-3000.service=project-web-3000
  - traefik.http.routers.project-web-3000.tls=true
  - traefik.http.routers.project-web-3000.tls.certresolver=letsencrypt
  - traefik.http.services.project-web-3000.loadbalancer.server.port=3000
```

**Note on TCP/UDP**: TCP/UDP routing is NOT emitted as compose labels (that path is intentionally disabled in `inject_traefik_labels`). TCP/UDP routers are rendered into the dynamic config files (`proxy/traefik/dynamic/routers-tcp.yml` / `routers-udp.yml`) from `tpl/routers-tcp.yml.j2` / `routers-udp.yml.j2`, and any new entrypoints are generated into `proxy/traefik/traefik.yml`. Use `router: tcp` (or `udp`) with `hostport`/`passthrough` and run `itsup apply proxy`.

#### Host-Only Project Example

```yaml
enabled: true
host: 192.168.1.10          # Service running on host, not containerized
ingress:
  - service: api
    domain: api.example.com
    port: 8080
    router: http
```

**Behavior**:
- No docker-compose.yml generation
- No deployment (no containers to deploy)
- Traefik routing still configured (proxies to host:port)

### itsup.yml Schema

These are the keys actually read by the code (`lib/data.py`, `bin/write_artifacts.py`):

```yaml
schemaVersion: string               # Config schema version (e.g., "2.1.0")

traefikDomain: string               # REQUIRED. Traefik dashboard domain (write_dynamic_routers)

routerIP: string                    # Router IP; blank => netifaces auto-detect, written back here.
                                    # Used to build Traefik trusted IPs.

# Backup configuration (bin/backup.py reads exclude; s3 values come from secrets)
backup:
  exclude: [string]                 # project names to exclude from backup
  s3:
    host: string                    # ${AWS_S3_HOST}
    region: string                  # ${AWS_S3_REGION}
    bucket: string                  # ${AWS_S3_BUCKET}

# CrowdSec (write_middleware_config)
crowdsec:
  enabled: boolean
  apikey: string                    # ${CROWDSEC_APIKEY}
  collections: [string]

# Component version pinning (proxy compose template)
versions:
  traefik: string                   # Traefik image tag (e.g., v3.5.4)
  crowdsec: string                  # CrowdSec image tag
```

There is no `router_ip` (snake_case), `monitoring`, `dns`, `backup.prefix`, `include_volumes`, or `compression` key — those were never read by the code.

## Configuration Patterns

### Environment Variables

**In docker-compose.yml**:
```yaml
services:
  app:
    environment:
      # From secrets file
      - DB_HOST=${DB_HOST}
      - DB_PASSWORD=${DB_PASSWORD}

      # Hard-coded (not sensitive)
      - NODE_ENV=production
      - PORT=3000

      # Computed (from other vars)
      - DATABASE_URL=postgres://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:5432/${DB_NAME}
```

**In secrets/{project}.txt**:
```bash
DB_HOST=postgres
DB_USER=app
DB_PASSWORD=secretpass
DB_NAME=myapp
```

**Result**: Docker Compose expands `${VAR}` at runtime.

### Volumes

**Persistent Data**:
```yaml
services:
  db:
    volumes:
      - postgres-data:/var/lib/postgresql/data

volumes:
  postgres-data:
    driver: local
```

**Host Bind Mounts**:
```yaml
services:
  web:
    volumes:
      - ./html:/usr/share/nginx/html:ro
      - ./config.json:/app/config.json:ro
```

**Important**:
- Relative paths are relative to upstream/{project}/ (generated dir)
- Use absolute paths or named volumes for reliability

### Networks

**Standard Pattern** (all projects):
```yaml
services:
  app:
    networks:
      - proxynet

networks:
  proxynet:
    external: true
```

**Custom Networks** (internal only):
```yaml
services:
  app:
    networks:
      - proxynet  # External (Traefik access)
      - backend   # Internal (database access)

  db:
    networks:
      - backend   # Internal only (no Traefik access)

networks:
  proxynet:
    external: true
  backend:
    driver: bridge
```

### Health Checks

**HTTP Health Check**:
```yaml
services:
  api:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s  # Grace period for slow startup
```

**TCP Health Check**:
```yaml
healthcheck:
  test: ["CMD", "nc", "-z", "localhost", "5432"]
  interval: 10s
  timeout: 5s
  retries: 3
```

**Script Health Check**:
```yaml
healthcheck:
  test: ["CMD", "/app/healthcheck.sh"]
  interval: 30s
  timeout: 10s
  retries: 3
```

### Traefik Middleware

**Define in projects/traefik.yml**:
```yaml
http:
  middlewares:
    # Rate limiting
    rate-limit:
      rateLimit:
        average: 100
        burst: 50
        period: 1m

    # Basic auth
    auth:
      basicAuth:
        users:
          - "admin:$apr1$H6uskkkW$IgXLP6ewTrSuBkTrqE8wj/"

    # Headers
    security-headers:
      headers:
        stsSeconds: 31536000
        stsIncludeSubdomains: true
        stsPreload: true
        forceSTSHeader: true

    # IP whitelist
    ip-whitelist:
      ipWhiteList:
        sourceRange:
          - "192.168.1.0/24"
          - "10.0.0.0/8"
```

**Applying middleware**: there is no `middleware` field on an ingress row. Middlewares are defined in `projects/middlewares.yml` (merged into `proxy/traefik/dynamic/middlewares.yml`) and attached to a router either through Traefik's dynamic config or via explicit `traefik.http.routers.*.middlewares=...` labels added in the service's `labels:` list in `docker-compose.yml`:
```yaml
# in projects/{project}/docker-compose.yml
services:
  admin:
    labels:
      - traefik.http.routers.project-admin-8080.middlewares=auth@file,ip-whitelist@file
```

### Multi-Service Projects

**docker-compose.yml**:
```yaml
services:
  frontend:
    image: nginx:latest
    networks:
      - proxynet
      - backend

  api:
    image: node:20-alpine
    networks:
      - proxynet
      - backend

  db:
    image: postgres:16
    networks:
      - backend  # Not exposed to Traefik

networks:
  proxynet:
    external: true
  backend:
    driver: bridge
```

**itsup-project.yml** (multiple routes):
```yaml
enabled: true
ingress:
  - service: frontend
    domain: app.example.com
    port: 80
    router: http

  - service: api
    domain: api.example.com
    port: 3000
    router: http
```

**Result**: Two domains, one project.

## Configuration Best Practices

### Security

1. **Never commit secrets**: Only `.enc.txt` files in git
2. **Use strong secrets**: Generate with `openssl rand -hex 32`
3. **Minimize exposed ports**: Only expose what's needed via Traefik
4. **Use health checks**: Ensure only healthy containers receive traffic
5. **Enable HTTPS**: Always use `web-secure` entrypoint
6. **Rate limit APIs**: Add rate-limit middleware to prevent abuse

### Reliability

1. **Pin versions**: Use specific image tags (not `latest`)
2. **Set resource limits**: Prevent container resource exhaustion
3. **Configure restarts**: Use `restart: unless-stopped`
4. **Use health checks**: Enable automatic container recovery
5. **Enable logging**: Configure log drivers for debugging

### Maintainability

1. **Use comments**: Document non-obvious configuration
2. **Consistent naming**: Follow naming conventions (project-service-component)
3. **Group related config**: Keep related services in same project
4. **Use overrides**: Don't duplicate full Traefik config, only override needed parts
5. **Version control**: Commit all configuration changes

## Advanced Configuration

### Custom Entrypoints

**Add in projects/traefik.yml**:
```yaml
entryPoints:
  mqtt:
    address: ":1883"

  websocket:
    address: ":8080"
    transport:
      respondingTimeouts:
        idleTimeout: 3600s
```

**Use in itsup-project.yml**: there is no `entrypoint` field on an ingress row. For TCP/UDP routers, the entrypoint is generated automatically from `hostport` (see `write_traefik_config`). Declare the host port and the generator creates the matching entrypoint:
```yaml
ingress:
  - service: mqtt-broker
    domain: mqtt.example.com
    port: 1883
    hostport: 1883
    router: tcp
```

### TLS Configuration

**Custom TLS options in projects/traefik.yml**:
```yaml
tls:
  options:
    modern:
      minVersion: VersionTLS13
      cipherSuites:
        - TLS_AES_256_GCM_SHA384
        - TLS_CHACHA20_POLY1305_SHA256

    default:
      minVersion: VersionTLS12
```

**Use in ingress**:
```yaml
# Would require custom label injection (not currently supported in itsup-project.yml)
# Workaround: Add labels directly in docker-compose.yml
```

### Service Discovery

**Traefik automatically discovers** containers with:
- Label: `traefik.enable=true`
- Connected to `proxynet` network

**Manual discovery** (for host services):
```yaml
# In projects/traefik.yml (dynamic config)
http:
  services:
    external-service:
      loadBalancer:
        servers:
          - url: "http://192.168.1.100:8080"

  routers:
    external:
      rule: "Host(`external.example.com`)"
      service: external-service
      entryPoints: [web-secure]
      tls:
        certResolver: letsencrypt
```

### Load Balancing

**Multiple replicas** (Docker Compose scale):
```yaml
services:
  api:
    image: my-api:latest
    deploy:
      replicas: 3
    networks:
      - proxynet
```

**Manual servers** (external services):
```yaml
# In projects/traefik.yml
http:
  services:
    api-cluster:
      loadBalancer:
        servers:
          - url: "http://192.168.1.10:3000"
          - url: "http://192.168.1.11:3000"
          - url: "http://192.168.1.12:3000"
```

### Sticky Sessions

```yaml
# In projects/traefik.yml
http:
  services:
    my-service:
      loadBalancer:
        sticky:
          cookie:
            name: server_id
            secure: true
            httpOnly: true
```

## Configuration Validation

### Manual Validation

**Validate YAML syntax**:
```bash
# Check docker-compose.yml
docker compose -f projects/{project}/docker-compose.yml config

# Check itsup-project.yml (Python YAML parser)
python -c "import yaml; yaml.safe_load(open('projects/{project}/itsup-project.yml'))"
```

**Validate Traefik config**:
```bash
# Dry-run Traefik with config
docker run --rm -v $PWD/proxy/traefik:/etc/traefik:ro \
  traefik:v3.6.17 traefik --configFile=/etc/traefik/traefik.yml --dryRun
```

### Automated Validation

**CLI validation** (recommended):
```bash
itsup validate              # Validate all projects
itsup validate {project}    # Validate specific project
```

**Pre-commit hook** (prevent bad commits):
```bash
#!/bin/bash
# .git/hooks/pre-commit
source env.sh
itsup validate
if [ $? -ne 0 ]; then
  echo "Configuration validation failed!"
  exit 1
fi
```

## Troubleshooting Configuration

### Common Issues

**Problem**: Service not reachable via domain

**Check**:
1. Verify itsup-project.yml is correct: `cat projects/{project}/itsup-project.yml`
2. Check generated labels: `grep "traefik.http.routers" upstream/{project}/docker-compose.yml`
3. Verify service is running: `itsup svc {project} ps`
4. Check Traefik logs: `itsup proxy logs traefik | grep {project}`

**Problem**: Secrets not expanding in containers

**Check**:
1. Verify secrets file exists: `cat secrets/{project}.txt`
2. Check docker-compose.yml has `${VAR}` placeholders
3. Verify deployment loads secrets: `itsup apply {project}` (should load secrets)
4. Check environment in container: `docker exec {container} env | grep VAR`

**Problem**: Configuration changes not taking effect

**Check**:
1. Verify edited source, not generated: `ls -l projects/{project}/`
2. Force deployment by stopping first: `itsup svc {project} down && itsup apply {project}`
3. Check logs for errors: `itsup svc {project} logs`

## Configuration Examples

See `samples/` directory for complete examples:
- `samples/projects/itsup.yml`: Infrastructure config template
- `samples/projects/traefik.yml`: Traefik overrides template
- `samples/projects/example-project/`: Complete project example (`docker-compose.yml` + `itsup-project.yml`)
- `samples/secrets/itsup.txt`: Secrets file template
