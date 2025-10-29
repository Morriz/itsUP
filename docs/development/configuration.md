# Configuration Guide

Comprehensive guide to configuring itsup infrastructure and projects.

## Configuration Files Overview

### Infrastructure Configuration

**`projects/itsup.yml`**:
```yaml
# Router configuration
router_ip: 192.168.1.1

# Version pinning
versions:
  traefik: v3.5.1
  crowdsec: latest

# Backup configuration
backup:
  s3:
    bucket: my-backup-bucket
    prefix: itsup/
    region: us-east-1
  include_volumes: false
  compression: true

# Monitoring
monitoring:
  enabled: true
  opensnitch: true
```

**Purpose**:
- Global infrastructure settings
- Shared across all projects
- Secrets as `${VAR}` placeholders (expanded from `secrets/itsup.txt`)

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
      - proxynet
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost/health"]
      interval: 30s
      timeout: 5s
      retries: 3

networks:
  proxynet:
    external: true
```

**Purpose**:
- Standard Docker Compose file
- Service definitions (images, volumes, networks)
- Secrets as `${VAR}` placeholders

**`projects/{project}/ingress.yml`**:
```yaml
enabled: true
ingress:
  - service: web
    domain: example.com
    port: 80
    router: http
    middleware: [rate-limit]  # Optional
```

**Purpose**:
- Routing configuration (IngressV2 schema)
- Auto-generates Traefik labels
- Simpler than manual label management

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
- Loaded in order: itsup.txt → {project}.txt (later overrides earlier)
- Encrypted with SOPS for git storage

## Configuration Schema Reference

### IngressV2 Schema (ingress.yml)

```yaml
enabled: boolean                    # Enable/disable routing for this project

# Optional: For host-only projects (no containers)
host: string                        # Host IP (e.g., 192.168.1.5)

# Routing rules (list)
ingress:
  - service: string                 # Service name from docker-compose.yml
    domain: string                  # Domain name (e.g., app.example.com)
    port: integer                   # Service port
    router: "http" | "tcp"          # Router type

    # Optional fields
    middleware: [string]            # List of Traefik middleware names

    # TLS configuration (for TCP passthrough)
    tls:
      passthrough: boolean          # Enable TCP TLS passthrough (default: false)
```

#### HTTP Router Example

```yaml
enabled: true
ingress:
  - service: web
    domain: my-app.example.com
    port: 3000
    router: http
    middleware: [rate-limit, auth]
```

**Generates**:
```yaml
labels:
  - traefik.enable=true
  - traefik.http.routers.project-web.rule=Host(`my-app.example.com`)
  - traefik.http.routers.project-web.entrypoints=web,web-secure
  - traefik.http.routers.project-web.tls.certresolver=letsencrypt
  - traefik.http.routers.project-web.middlewares=rate-limit,auth
  - traefik.http.services.project-web.loadbalancer.server.port=3000
```

#### TCP Router Example (TLS Passthrough)

```yaml
enabled: true
ingress:
  - service: secure-app
    domain: secure.example.com
    port: 8123
    router: tcp
    tls:
      passthrough: true
```

**Generates**:
```yaml
labels:
  - traefik.enable=true
  - traefik.tcp.routers.project-secure-app.rule=HostSNI(`secure.example.com`)
  - traefik.tcp.routers.project-secure-app.entrypoints=tcp
  - traefik.tcp.routers.project-secure-app.tls.passthrough=true
  - traefik.tcp.services.project-secure-app.loadbalancer.server.port=8123
```

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

```yaml
# Network configuration
router_ip: string                   # Router IP address (e.g., 192.168.1.1)
                                    # Used to determine trusted subnet

# Version pinning
versions:
  traefik: string                   # Traefik image tag (e.g., v3.5.1)
  crowdsec: string                  # CrowdSec image tag (optional)

# Backup configuration
backup:
  s3:
    bucket: string                  # S3 bucket name
    prefix: string                  # Key prefix (e.g., itsup/)
    region: string                  # AWS region
  include_volumes: boolean          # Backup container volumes?
  compression: boolean              # Use gzip compression?

# Monitoring
monitoring:
  enabled: boolean                  # Enable container security monitor
  opensnitch: boolean               # Enable OpenSnitch integration
  report_only: boolean              # Detection only, no blocking

# Optional: DNS configuration
dns:
  honeypot: boolean                 # Enable DNS honeypot
  upstream: [string]                # Upstream DNS servers
```

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

**Reference in ingress.yml**:
```yaml
ingress:
  - service: admin
    domain: admin.example.com
    port: 8080
    router: http
    middleware: [auth, ip-whitelist, security-headers]
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

**ingress.yml** (multiple routes):
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
    middleware: [rate-limit]
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

**Use in ingress.yml**:
```yaml
ingress:
  - service: mqtt-broker
    domain: mqtt.example.com
    port: 1883
    router: tcp
    entrypoint: mqtt  # Custom entrypoint
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
# Would require custom label injection (not currently supported in ingress.yml)
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

# Check ingress.yml (Python YAML parser)
python -c "import yaml; yaml.safe_load(open('projects/{project}/ingress.yml'))"
```

**Validate Traefik config**:
```bash
# Dry-run Traefik with config
docker run --rm -v $PWD/proxy/traefik:/etc/traefik:ro \
  traefik:v3.5.1 traefik --configFile=/etc/traefik/traefik.yml --dryRun
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
1. Verify ingress.yml is correct: `cat projects/{project}/ingress.yml`
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
2. Force regeneration: `rm projects/{project}/.config_hash && itsup apply {project}`
3. Check logs for errors: `itsup svc {project} logs`

## Configuration Examples

See `samples/` directory for complete examples:
- `samples/itsup.yml`: Infrastructure config template
- `samples/traefik.yml`: Traefik overrides template
- `samples/example-project/`: Complete project example
- `samples/secrets/itsup.txt`: Secrets file template
