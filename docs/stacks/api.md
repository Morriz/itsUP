# API Stack

The API provides the web interface and REST endpoints for managing the itsup infrastructure.

## Overview

**Purpose**: Web-based management interface for infrastructure operations.

**Technology**: Python FastAPI application running as a host process (not containerized).

**Access**: `https://api.srv.instrukt.ai`

**Port**: 8080 (local only, proxied through Traefik)

## Architecture

### Why Not Containerized?

The API runs as a host process for several reasons:

1. **Direct System Access**: Needs to manage Docker, systemd services, and system files
2. **Zero-Downtime Deployments**: Traefik runs on host network for scaling deployments
3. **Operational Flexibility**: Easier debugging and log access during incidents
4. **Consistency**: CLI and API share the same codebase and environment

### Host-Only Configuration

```yaml
# projects/itsup/ingress.yml
enabled: true
host: 192.168.1.x  # Router IP (dynamic)
ingress:
  - service: api
    domain: api.srv.instrukt.ai
    port: 8080
    router: http
```

This configuration:
- Has no `docker-compose.yml` (no containers)
- Skips artifact generation
- Still generates Traefik routing config for reverse proxy

## Components

### FastAPI Application

**Location**: `api/` directory (exact structure TBD)

**Key Features**:
- REST API for infrastructure operations
- Web UI for monitoring and management
- Real-time log streaming
- Project deployment triggers
- Health checks and status monitoring

**Endpoints** (examples, actual API may vary):
```
GET  /health              # Health check
GET  /projects            # List all projects
POST /projects/{name}/deploy  # Deploy project
GET  /projects/{name}/logs    # Stream project logs
GET  /stacks/{name}/status    # Stack status
POST /stacks/{name}/restart   # Restart stack
```

### Process Management

**Start**: `bin/start-api.sh` (systemd service recommended)

**Stop**: Kill Python process or use systemd

**Logs**: `logs/api.log` (rotated via logrotate)

## Deployment

### Manual Start
```bash
# From project root
bin/start-api.sh
```

### Systemd Service (Recommended)

Create `/etc/systemd/system/itsup-api.service`:

```ini
[Unit]
Description=itsUP Infrastructure API
After=network.target docker.service

[Service]
Type=simple
User=morriz
WorkingDirectory=/home/morriz/srv
ExecStart=/home/morriz/srv/bin/start-api.sh
Restart=always
RestartSec=10
StandardOutput=append:/home/morriz/srv/logs/api.log
StandardError=append:/home/morriz/srv/logs/api.log

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable itsup-api
sudo systemctl start itsup-api
sudo systemctl status itsup-api
```

### Dependencies

**Requires**:
- Python virtual environment (`.venv/`)
- `secrets/itsup.txt` for environment variables
- Proxy stack (Traefik for routing)
- Docker daemon

**Start Order**:
1. DNS stack (creates proxynet network)
2. Proxy stack (Traefik)
3. API (can start anytime after proxy is up)

## Configuration

### Secrets

Loaded from `secrets/itsup.txt`:
```bash
# API-specific secrets
API_SECRET_KEY=...
API_ADMIN_TOKEN=...

# Shared infrastructure secrets
ROUTER_IP=...
```

### Environment Variables

The API inherits environment from:
1. Shell environment (from `bin/start-api.sh`)
2. `secrets/itsup.txt` (loaded via `lib/data.py:get_env_with_secrets()`)
3. `.env` file (if present)

## Logging

### API Logs

**File**: `logs/api.log`

**Format**: Structured JSON or plain text (application-dependent)

**Rotation**:
- Method: `copytruncate` (Python process keeps writing to same file)
- Size: 10M per rotation
- Keep: 5 rotations
- Compression: gzip (delayed)

**View**:
```bash
tail -f logs/api.log                    # Follow live logs
grep "ERROR" logs/api.log               # Search for errors
zgrep "pattern" logs/api.log*.gz        # Search compressed logs
```

See [Logging Documentation](../operations/logging.md) for details.

## Security

### Authentication

API should implement authentication for all management endpoints:
- Admin token from `secrets/itsup.txt`
- Session-based auth for web UI
- API key auth for programmatic access

### Authorization

Recommended RBAC model:
- **Admin**: Full access (deploy, restart, configure)
- **Operator**: Read/monitor access + safe operations (logs, status)
- **Viewer**: Read-only access

### Network Security

- **Bind Address**: 127.0.0.1 (local only)
- **External Access**: Only via Traefik reverse proxy
- **TLS**: Terminated at Traefik (Let's Encrypt certificates)
- **Rate Limiting**: Should be configured via Traefik middleware

### Input Validation

API must validate all inputs to prevent:
- Command injection (especially for project names, service names)
- Path traversal (file access endpoints)
- Resource exhaustion (unbounded log streaming)

## Monitoring

### Health Checks

**Endpoint**: `GET /health`

**Traefik Configuration**:
```yaml
# In proxy/traefik/api-log.conf.yaml
http:
  services:
    itsup-api:
      loadBalancer:
        servers:
          - url: "http://192.168.1.x:8080"
        healthCheck:
          path: /health
          interval: 30s
          timeout: 5s
```

### Metrics (Future)

Consider adding metrics endpoints:
- Request rates and latencies
- Deployment success/failure counts
- Active project status
- Container resource usage

## Troubleshooting

### API Not Responding

**Check if running**:
```bash
ps aux | grep "python.*api"
sudo systemctl status itsup-api  # If using systemd
```

**Check port binding**:
```bash
netstat -tlnp | grep :8080
# Should show Python process listening on 127.0.0.1:8080
```

**Check logs**:
```bash
tail -100 logs/api.log
# Look for startup errors, exceptions
```

### Cannot Access via Domain

**Verify Traefik routing**:
```bash
itsup proxy logs traefik | grep itsup-api
# Should show service registered
```

**Check ingress config**:
```bash
cat projects/itsup/ingress.yml
# Verify domain, port, host IP correct
```

**Test direct access** (should work):
```bash
curl http://localhost:8080/health
```

**Test via Traefik** (should work):
```bash
curl -H "Host: api.srv.instrukt.ai" http://localhost/health
```

### High Memory Usage

Python processes can accumulate memory over time:

**Solution**: Restart the API
```bash
sudo systemctl restart itsup-api
```

**Prevention**: Consider setting memory limits in systemd:
```ini
[Service]
MemoryMax=512M
MemoryHigh=400M
```

### Log Rotation Issues

If API stops logging after rotation:

**Check copytruncate** is enabled in `/etc/logrotate.d/itsup`:
```
/home/morriz/srv/logs/api.log {
  copytruncate  # Required for Python processes
  ...
}
```

Python processes don't handle log rotation signals, so `copytruncate` is mandatory.

## Development

### Local Testing

```bash
# Activate venv
source .venv/bin/activate

# Load secrets
export $(grep -v '^#' secrets/itsup.txt | xargs)

# Run API directly
python -m api.main  # Or however API is structured
```

### Code Structure (Example)

```
api/
├── main.py           # FastAPI app entry point
├── routes/
│   ├── projects.py   # Project management endpoints
│   ├── stacks.py     # Stack management endpoints
│   └── health.py     # Health check endpoint
├── models/
│   └── schemas.py    # Pydantic models
└── services/
    ├── docker.py     # Docker operations wrapper
    └── deploy.py     # Deployment logic
```

### Testing

API should have comprehensive tests:

```bash
# Unit tests
bin/test.sh  # Runs all *_test.py files

# Integration tests (if API has them)
pytest api/tests/integration/
```

## Future Improvements

- **WebSocket Support**: Real-time log streaming and status updates
- **Metrics Collection**: Prometheus-compatible metrics endpoint
- **Event Streaming**: Server-sent events for deployment progress
- **Audit Logging**: Track all management operations with user attribution
- **Role-Based Access**: Fine-grained permission system
- **API Documentation**: OpenAPI/Swagger UI for interactive API docs
