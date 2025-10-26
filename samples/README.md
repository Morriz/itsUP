# itsUP Projects Configuration

This directory contains configuration for your infrastructure and deployed services.

## Directory Structure

```
projects/
├── itsup.yml                    # Infrastructure config
├── traefik.yml                  # Traefik overrides
├── example-project/             # Example project structure
│   ├── docker-compose.yml       # Service definitions
│   └── ingress.yml              # Routing configuration
├── myapp/                       # Your project
│   ├── docker-compose.yml
│   └── ingress.yml
└── another-service/
    ├── docker-compose.yml
    └── ingress.yml
```

## Configuration Files

### `itsup.yml` - Infrastructure Configuration

Core infrastructure settings (versions, backup, network):

```yaml
# Router IP (auto-detected or manually set)
routerIP: 192.168.1.1

# Service versions
versions:
  traefik: v3.2
  crowdsec: v1.6.8

# S3 backup configuration (optional)
backup:
  exclude: []  # Projects to skip in backups
  s3:
    host: ${AWS_S3_HOST}      # from secrets/itsup.txt
    region: ${AWS_S3_REGION}
    bucket: ${AWS_S3_BUCKET}
```

**Secrets**: Use `${VAR}` placeholders - values loaded from `secrets/itsup.txt`

### `traefik.yml` - Traefik Overrides

Custom Traefik configuration merged on top of generated config:

```yaml
# Uses native Traefik YAML schema
certificatesResolvers:
  letsencrypt:
    acme:
      email: ${LETSENCRYPT_EMAIL}

log:
  level: INFO  # DEBUG, INFO, WARN, ERROR

middlewares:
  rate-limit:
    rateLimit:
      average: 100
      burst: 200

plugins:
  crowdsec:
    enabled: true
    apikey: ${CROWDSEC_APIKEY}
    collections:
      - crowdsecurity/traefik
      - crowdsecurity/http-cve
```

**See**: [Traefik Documentation](https://doc.traefik.io/traefik/) for all options

## Project Structure

Each project has two files:

### `docker-compose.yml` - Service Definitions

Standard Docker Compose format with secrets as `${VAR}` placeholders:

```yaml
services:
  web:
    image: nginx:latest
    environment:
      - API_KEY=${MY_API_KEY}  # from secrets/myproject.txt
    volumes:
      - ./data:/usr/share/nginx/html
    networks:
      - proxynet

networks:
  proxynet:
    external: true
```

**Important**:
- Services needing ingress **must** connect to `proxynet` network
- Secrets: Use `${VAR}` - loaded from `secrets/{project}.txt`
- Use relative paths for volumes (relative to `upstream/{project}/`)

### `ingress.yml` - Routing Configuration

Simplified routing config (auto-generates Traefik labels):

```yaml
enabled: true

ingress:
  # Simple HTTP service
  - service: web
    domain: myapp.example.com
    port: 80
    router: http

  # TCP passthrough (e.g., SSH)
  - service: ssh
    port: 2222
    router: tcp
    hostport: 2222

  # UDP service (e.g., WireGuard)
  - service: vpn
    port: 51820
    router: udp
    hostport: 51820
```

**Router types**:
- `http` - HTTP/HTTPS with automatic TLS
- `tcp` - TCP passthrough (requires `hostport`)
- `udp` - UDP passthrough (requires `hostport`)

**Auto-generated**: Traefik labels are injected into `upstream/{project}/docker-compose.yml`

## Quick Start

### 1. Initialize Configuration

```bash
# First-time setup (copies samples to projects/)
itsup init
```

### 2. Create a New Project

```bash
# Copy example structure
cp -r projects/example-project projects/myapp

# Edit configuration
vim projects/myapp/docker-compose.yml
vim projects/myapp/ingress.yml
```

### 3. Add Secrets

```bash
# Create/edit project secrets
itsup edit-secret myapp
```

Add secrets in `KEY=value` format:
```bash
DB_PASSWORD=supersecret
API_KEY=abc123
ADMIN_TOKEN=xyz789
```

### 4. Deploy

```bash
# Validate configuration
itsup validate myapp

# Deploy single project
itsup apply myapp

# Deploy all projects
itsup apply
```

## Managing Projects

### Deploy & Update

```bash
itsup apply              # Deploy all projects (parallel)
itsup apply myapp        # Deploy single project
itsup svc myapp up       # Start project services
itsup svc myapp restart  # Restart project
```

### Monitor & Debug

```bash
itsup svc myapp logs -f          # Tail all logs
itsup svc myapp logs -f web      # Tail specific service
itsup svc myapp ps               # Show status
itsup svc myapp exec web sh      # Shell into container
```

### Validation

```bash
itsup validate           # Validate all projects
itsup validate myapp     # Validate single project
```

## Working with Git

Projects are stored in a git submodule:

```bash
# Commit changes
itsup commit "feat: add new service"

# Check status
itsup status

# Force push (skip rebase)
itsup commit -f "fix: override remote"
```

## Secrets Management

Project secrets are loaded from `secrets/{project}.txt`:

```bash
# Edit project secrets (auto-encrypted)
itsup edit-secret myapp

# View loaded secrets (DEBUG mode)
export LOG_LEVEL=DEBUG
itsup apply myapp  # Shows decryption details
```

**Loading order** (later overrides earlier):
1. `secrets/itsup.txt` - Global secrets
2. `secrets/{project}.txt` - Project-specific secrets

## Advanced Configuration

### Custom Networks

Projects can use custom networks beyond `proxynet`:

```yaml
# docker-compose.yml
services:
  app:
    networks:
      - proxynet    # For ingress
      - internal    # Private network

networks:
  proxynet:
    external: true
  internal:
    driver: bridge
```

### Health Checks

Add health checks for better monitoring:

```yaml
services:
  web:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Resource Limits

```yaml
services:
  web:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G
```

## Artifact Generation

When you run `itsup apply`, artifacts are generated:

```
upstream/{project}/
└── docker-compose.yml    # Original + injected Traefik labels

proxy/
├── docker-compose.yml    # Traefik stack
└── traefik/
    ├── traefik.yml       # Generated + traefik.yml overrides
    └── dynamic/
        ├── routers-http.yml
        ├── routers-tcp.yml
        └── routers-udp.yml
```

**Do not edit generated files** - they're overwritten on every `itsup apply`

## Troubleshooting

### "Project not found"

Project directory must exist in `projects/`:
```bash
ls -la projects/myapp
```

### Routing not working

1. Check ingress is enabled: `enabled: true` in `ingress.yml`
2. Verify service is on `proxynet`: `docker network inspect proxynet`
3. Check Traefik logs: `itsup proxy logs traefik`

### Secrets not loading

1. Verify secret file exists: `ls secrets/myapp.enc.txt`
2. Decrypt manually: `itsup decrypt myapp`
3. Check format: `KEY=value` (no spaces, one per line)

### Container won't start

```bash
# Check service logs
itsup svc myapp logs service-name

# Validate compose file
itsup validate myapp

# Check docker compose directly
docker compose -f upstream/myapp/docker-compose.yml config
```

## Best Practices

1. **Use semantic names** - `myapp`, not `app1` or `test`
2. **One concern per project** - Don't mix unrelated services
3. **Pin image versions** - `nginx:1.24` not `nginx:latest`
4. **Add health checks** - Enables automatic recovery
5. **Use relative paths** - Makes projects portable
6. **Validate before deploy** - `itsup validate` catches errors early
7. **Commit incrementally** - Small, focused changes
8. **Document custom configs** - Add comments to docker-compose.yml
9. **Test locally first** - Verify docker-compose.yml works standalone
10. **Keep secrets minimal** - Only store what's truly secret

## Example: Full Project Setup

```bash
# 1. Create project structure
mkdir -p projects/myapp
cat > projects/myapp/docker-compose.yml <<EOF
services:
  web:
    image: nginx:1.24
    environment:
      - API_KEY=\${API_KEY}
    networks:
      - proxynet

networks:
  proxynet:
    external: true
EOF

cat > projects/myapp/ingress.yml <<EOF
enabled: true
ingress:
  - service: web
    domain: myapp.example.com
    port: 80
    router: http
EOF

# 2. Add secrets
itsup edit-secret myapp
# Add: API_KEY=secret123

# 3. Validate
itsup validate myapp

# 4. Deploy
itsup apply myapp

# 5. Check logs
itsup svc myapp logs -f

# 6. Commit
itsup commit "feat: add myapp service"
```

Now visit `https://myapp.example.com` 🎉
