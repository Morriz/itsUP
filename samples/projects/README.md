# itsUP Project Configurations

Shareable itsUP configurations to quickly deploy docker compose stacks with predefined ingress for traefik. This repo Should be placed in the `projects/` directory of your itsUP setup. (see [itsUP readme](https://github.com/itsup/itsup))

All `${VAR}` placeholders are replaced with values from the `itsUP-secrets` repo. (Should be placed in the `secrets/` directory.)

## Overview

The `projects/` directory contains all infrastructure and service configurations for itsUP. Each project follows a standard structure with `docker-compose.yml` (service definitions) and `ingress.yml` (routing configuration).

## Structure

```
projects/
├── itsup.yml                    # Global infrastructure config
├── traefik.yml                  # Traefik overrides (merged on generated base)
└── {project}/
    ├── docker-compose.yml       # Service definitions (secrets as ${VAR})
    └── ingress.yml              # Routing configuration (IngressV2 schema)
```

## Configuration Files

### Global Configuration

**`itsup.yml`** - Infrastructure settings:

```yaml
# Network configuration
router_ip: 192.168.1.1

# Version pinning
versions:
  traefik: v3.5.1

# Backup configuration
backup:
  s3:
    host: ${AWS_S3_HOST}
    region: ${AWS_S3_REGION}
    bucket: ${AWS_S3_BUCKET}
```

**`traefik.yml`** - Traefik overrides:

```yaml
# Custom middlewares
http:
  middlewares:
    rate-limit:
      rateLimit:
        average: 100
        burst: 50
```

### Project Configuration

**`docker-compose.yml`** - Standard Docker Compose file:

```yaml
services:
  web:
    image: nginx:latest
    environment:
      - DOMAIN=${DOMAIN} # From secrets/
    volumes:
      - ./html:/usr/share/nginx/html:ro
    networks:
      - proxynet

networks:
  proxynet: # this makes it accessible to traefik
    external: true
```

**`ingress.yml`** - Routing configuration (IngressV2 schema):

```yaml
enabled: true
ingress:
  - service: web
    domain: example.com
    port: 8080
    router: http
```

## IngressV2 Schema

Complete schema reference for `ingress.yml`:

```yaml
enabled: boolean                    # Enable/disable routing

# Optional: For host-only services (no containers)
host: string                        # Host IP (e.g., 192.168.1.5)

# Routing rules (list)
ingress:
  - service: string                 # Service name from docker-compose.yml
    domain: string                  # Domain name
    port: integer                   # Service port
    router: "http" | "tcp"          # Router type

    # Optional fields
    middleware: [string]            # Traefik middleware names

    # TLS passthrough (TCP only)
    tls:
      passthrough: boolean          # Enable TLS passthrough
```

## Common Patterns

### HTTP Service

**docker-compose.yml:**

```yaml
services:
  web:
    image: nginx:latest
    networks:
      - proxynet

networks:
  proxynet:
    external: true
```

**ingress.yml:**

```yaml
enabled: true
ingress:
  - service: web
    domain: app.example.com
    port: 8080
    router: http
```

**Generates Traefik labels:**

```yaml
labels:
  - traefik.enable=true
  - traefik.http.routers.project-web.rule=Host(`app.example.com`)
  - traefik.http.routers.project-web.tls.certresolver=letsencrypt
  - traefik.http.services.project-web.loadbalancer.server.port=80
```

### TCP Service

**ingress.yml:**

```yaml
enabled: true
ingress:
  - service: api
    domain: api.example.com
    port: 9000
    router: tcp
```

### TLS Passthrough (No Termination)

**ingress.yml:**

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

### Multi-Service Project

**docker-compose.yml:**

```yaml
services:
  frontend:
    image: nginx:latest
    networks:
      - proxynet

  api:
    image: node:20-alpine
    networks:
      - proxynet
      - backend

  db:
    image: postgres:16
    networks:
      - backend # Not exposed to Traefik

networks:
  proxynet:
    external: true
  backend:
    driver: bridge
```

**ingress.yml:**

```yaml
enabled: true
ingress:
  - service: frontend
    domain: app.example.com
    port: 8080
    router: http

  - service: api
    domain: api.example.com
    port: 3000
    router: http
    middleware: [rate-limit]
```

### Host-Only Service

For services running on host (not containerized):

**docker-compose.yml:**

```yaml
# Empty or minimal - no containers
services: {}
```

**ingress.yml:**

```yaml
enabled: true
host: 192.168.1.10 # Host IP where service runs
ingress:
  - service: api
    domain: api.example.com
    port: 8080
    router: http
```

**Behavior:**

- No artifact generation in `upstream/`
- No deployment (no containers)
- Traefik routing still configured (proxies to host:port)

## Secrets Management

### Using Secrets in Projects

**In docker-compose.yml:**

```yaml
services:
  app:
    environment:
      # Simple reference
      - DB_PASSWORD=${DB_PASSWORD}

      # With default value
      - LOG_LEVEL=${LOG_LEVEL:-info}

      # Computed value
      - DATABASE_URL=postgres://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:5432/${DB_NAME}
```

**In secrets/{project}.txt:**

```bash
DB_HOST=postgres
DB_USER=app
DB_PASSWORD=secretpass
DB_NAME=myapp
```

### Loading Order

Secrets are loaded in order (later overrides earlier):

1. `secrets/itsup.txt` (shared infrastructure)
2. `secrets/{project}.txt` (project-specific)

## Deployment Workflow

### 1. Create Project Structure

```bash
# Create project directory
mkdir -p projects/my-app

# Create docker-compose.yml
cat > projects/my-app/docker-compose.yml <<EOF
services:
  web:
    image: nginx:latest
    networks:
      - proxynet
networks:
  proxynet:
    external: true
EOF

# Create ingress.yml
cat > projects/my-app/ingress.yml <<EOF
enabled: true
ingress:
  - service: web
    domain: my-app.example.com
    port: 8080
    router: http
EOF
```

### 2. (Optional) Add Project Secrets

```bash
# Create secrets file
cat > secrets/my-app.txt <<EOF
DOMAIN=my-app.example.com
API_KEY=abc123
EOF

# Encrypt
itsup encrypt my-app
```

### 3. Deploy

```bash
# Validate configuration
itsup validate my-app

# Deploy with smart rollout
itsup apply my-app
```

### 4. Verify

```bash
# Check containers
itsup svc my-app ps

# Check logs
itsup svc my-app logs -f

# Test endpoint
curl https://my-app.example.com
```

## Example Project

See `samples/projects/example-project/` for a complete working example with:

- Standard docker-compose.yml setup
- Ingress configuration
- Network configuration
- Health checks

## Advanced Patterns

### With Middleware

**Define in `traefik.yml`:**

```yaml
http:
  middlewares:
    auth:
      basicAuth:
        users:
          - 'admin:$apr1$H6uskkkW$IgXLP6ewTrSuBkTrqE8wj/'

    rate-limit:
      rateLimit:
        average: 100
        burst: 50
```

**Reference in `ingress.yml`:**

```yaml
ingress:
  - service: admin
    domain: admin.example.com
    port: 8080
    router: http
    middleware: [auth, rate-limit]
```

### With Health Checks

**In docker-compose.yml:**

```yaml
services:
  api:
    image: my-api:latest
    healthcheck:
      test: ['CMD', 'curl', '-f', 'http://localhost:8080/health']
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s
    networks:
      - proxynet
```

### With Volume Mounts

**In docker-compose.yml:**

```yaml
services:
  app:
    image: my-app:latest
    volumes:
      - app-data:/data
      - ./config:/app/config:ro
    networks:
      - proxynet

volumes:
  app-data:
    driver: local
```

## Migration from V1

If migrating from older itsup configurations:

**Old (V1):**

```yaml
# project.yml
enabled: true
domain: example.com
target: web:80
```

**New (V2):**

```yaml
# ingress.yml
enabled: true
ingress:
  - service: web
    domain: example.com
    port: 8080
    router: http
```

**Benefits of V2:**

- Multiple ingress entries per project
- Explicit router type (http/tcp)
- Middleware support
- TLS passthrough support
- Host-only service support

## Best Practices

1. **Pin image versions**: Use specific tags (not `latest`)

   ```yaml
   image: nginx:1.25.3-alpine
   ```

2. **Use health checks**: Enable automatic recovery

   ```yaml
   healthcheck:
     test: ['CMD', 'curl', '-f', 'http://localhost/health']
   ```

3. **Separate networks**: Internal services on separate network

   ```yaml
   networks:
     - proxynet # External (Traefik)
     - backend # Internal only
   ```

4. **Use secrets**: Never hard-code sensitive values

   ```yaml
   environment:
     - DB_PASSWORD=${DB_PASSWORD} # From secrets file
   ```

5. **Enable restarts**: Automatic recovery from crashes

   ```yaml
   restart: unless-stopped
   ```

6. **Validate before deploy**: Catch errors early
   ```bash
   itsup validate my-app
   ```

## Troubleshooting

### Service Not Reachable

**Check configuration:**

```bash
cat projects/my-app/ingress.yml
grep "traefik.enable" upstream/my-app/docker-compose.yml
```

**Check Traefik logs:**

```bash
itsup proxy logs traefik | grep my-app
```

### Secrets Not Loading

**Verify secrets file:**

```bash
cat secrets/my-app.txt | grep VAR
```

**Check container environment:**

```bash
docker exec {container} env | grep VAR
```

### Configuration Not Taking Effect

**Force deployment:**

```bash
itsup svc my-app down
itsup apply my-app
```

## Documentation

For complete documentation, see:

- [Configuration Guide](../../docs/development/configuration.md)
- [Deployment Guide](../../docs/operations/deployment.md)
- [CLI Reference](../../docs/reference/cli.md)
- [Troubleshooting](../../docs/reference/troubleshooting.md)
