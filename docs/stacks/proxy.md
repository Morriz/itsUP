# Proxy Stack

The proxy stack provides reverse proxy, TLS termination, and routing capabilities using Traefik v3.5.1.

## Components

### Traefik (v3.5.1)

**Purpose**: Layer 7 HTTP reverse proxy and Layer 4 TCP passthrough for TLS services.

**Key Features**:
- Automatic TLS certificate management (Let's Encrypt)
- Dynamic service discovery via Docker labels
- HTTP to HTTPS redirection
- TCP passthrough for services requiring end-to-end TLS
- Access logging with rotation
- Middleware support (authentication, rate limiting, headers)

**Configuration**:
- Base config: `proxy/traefik/traefik.yml` (generated from `lib/data.py:get_trusted_ips()`)
- User overrides: `projects/traefik.yml` (merged on top)
- Dynamic config: `proxy/traefik/api-log.conf.yaml` (access logging)

**Entrypoints**:
- `web` (80): HTTP entry, redirects to HTTPS
- `web-secure` (443): HTTPS entry with TLS termination
- `tcp` (8443): TCP passthrough for services with own TLS (e.g., Home Assistant)

**Trusted IPs**:
- `172.0.0.0/8`: Docker networks
- `192.168.1.0/24`: Router subnet (dynamic from router IP)

These are used for `forwardedHeaders` and `proxyProtocol` to trust X-Forwarded-* headers.

### dockerproxy

**Purpose**: Secure Docker socket proxy to limit Traefik's access to Docker API.

**Why Needed**: Traefik needs Docker API access for service discovery but should not have full socket access (security risk).

**Access Restrictions**:
- Read-only access
- Limited to containers and networks
- No access to volumes, images, or exec

**Configuration**: `proxy/docker-compose.yml`

## Deployment

### Start/Stop
```bash
itsup proxy up           # Start all services
itsup proxy up traefik   # Start only Traefik
itsup proxy down         # Stop all services
itsup proxy restart      # Restart all services
itsup proxy logs         # Tail all logs
itsup proxy logs traefik # Tail Traefik logs only
```

### Dependencies
- **Requires**: DNS stack (proxynet network)
- **Required by**: All upstream projects (need Traefik for routing)

### Secrets
Loaded from `secrets/itsup.txt` (shared infrastructure secrets).

## Routing Configuration

Upstream projects define routing in `projects/{project}/ingress.yml`:

```yaml
enabled: true
ingress:
  - service: web
    domain: my-app.example.com
    port: 3000
    router: http  # or tcp
    middleware: []  # Optional Traefik middlewares
```

This generates Traefik labels in `upstream/{project}/docker-compose.yml`:

```yaml
labels:
  - traefik.enable=true
  - traefik.http.routers.{project}-{service}.rule=Host(`{domain}`)
  - traefik.http.routers.{project}-{service}.tls.certresolver=letsencrypt
  - traefik.http.services.{project}-{service}.loadbalancer.server.port={port}
```

### TCP Passthrough

For services that need end-to-end TLS (no termination at Traefik):

```yaml
ingress:
  - service: web
    domain: example.com
    port: 8123
    router: tcp
    tls:
      passthrough: true
```

Generates:
```yaml
labels:
  - traefik.tcp.routers.{project}-{service}.rule=HostSNI(`{domain}`)
  - traefik.tcp.routers.{project}-{service}.tls.passthrough=true
  - traefik.tcp.services.{project}-{service}.loadbalancer.server.port={port}
```

## Host-Only Projects

Some projects run on the host (not containerized) but need Traefik routing:

```yaml
# projects/itsup/ingress.yml
enabled: true
host: 192.168.1.x  # Host IP
ingress:
  - service: api
    domain: api.srv.instrukt.ai
    port: 8080
    router: http
```

These projects:
- Have no `docker-compose.yml` in `projects/` directory
- Skip artifact generation in `bin/write_artifacts.py`
- Skip deployment in `lib/deploy.py`
- Still generate Traefik routing config in `proxy/traefik/api-log.conf.yaml`

## Logging

### Access Logs
- **File**: `logs/access.log`
- **Format**: Common Log Format (CLF)
- **Rotation**: logrotate (10M, 5 rotations, compressed)
- **Rotation Method**: USR1 signal to Traefik (zero-downtime log reopening)

See [Logging Documentation](../operations/logging.md) for details.

### Container Logs
- **Driver**: json-file
- **Max Size**: 10M per file
- **Max Files**: 3 rotations
- **View**: `itsup proxy logs` or `docker compose logs`

## Troubleshooting

### Certificate Issues

**Problem**: Let's Encrypt rate limit exceeded
```bash
# Check certificate status
itsup proxy logs traefik | grep -i "certificate"

# Remove stuck certificates (forces renewal)
rm proxy/traefik/acme.json
itsup proxy restart
```

### Service Not Reachable

**Problem**: Upstream service not accessible via domain

**Check**:
1. Verify ingress.yml configuration: `cat projects/{project}/ingress.yml`
2. Check generated labels: `grep -A 20 "labels:" upstream/{project}/docker-compose.yml`
3. Verify Traefik sees the service: `itsup proxy logs traefik | grep {project}`
4. Check service is running: `itsup svc {project} ps`

### Trusted IPs Issues

**Problem**: X-Forwarded-* headers not being trusted

**Check**:
```bash
# Verify current trusted IPs
grep -A 5 "trustedIPs:" proxy/traefik/traefik.yml

# Should show:
# - 172.0.0.0/8 (Docker)
# - 192.168.1.0/24 (router subnet)
```

If subnet is wrong, router IP detection may be incorrect. Check `itsup.yml` router_ip setting.

## Security

### Docker Socket Proxy
- Traefik never has direct Docker socket access
- All Docker API requests go through dockerproxy (read-only, limited scope)
- Reduces attack surface if Traefik is compromised

### TLS Configuration
- Automatic certificate management (Let's Encrypt)
- Certificates stored in `proxy/traefik/acme.json` (600 permissions)
- HTTP to HTTPS redirect enforced (except /health endpoints)
- Modern TLS configuration (TLS 1.2+ preferred)

### Rate Limiting
Can be configured via middleware in `projects/traefik.yml`:

```yaml
http:
  middlewares:
    rate-limit:
      rateLimit:
        average: 100
        burst: 50
```

Then reference in ingress.yml:
```yaml
ingress:
  - service: api
    middleware: [rate-limit]
```
