# API Stack

The API provides REST/webhook endpoints for managing the itsup infrastructure. It is headless — there is no web UI.

## Overview

**Purpose**: Headless REST/webhook API for infrastructure operations (deploy triggers, project listing).

**Technology**: Python FastAPI application running as a host process (not containerized).

**Access**: `https://itsup.srv.instrukt.ai`

**Port**: 8888, bound to `0.0.0.0` (proxied through Traefik; see `api/main.py`)

## Architecture

### Why Not Containerized?

The API runs as a host process for several reasons:

1. **Direct System Access**: Needs to manage Docker, systemd services, and system files
2. **Zero-Downtime Deployments**: Traefik runs on host network for scaling deployments
3. **Operational Flexibility**: Easier debugging and log access during incidents
4. **Consistency**: CLI and API share the same codebase and environment

### Host-Only Configuration

```yaml
# projects/itsup/itsup-project.yml
enabled: true
host: 127.0.0.1
ingress:
  - domain: itsup.srv.instrukt.ai
    port: 8888
    router: http
```

This configuration:
- Has no `docker-compose.yml` (no containers)
- Skips artifact generation
- Still generates Traefik routing config that reverse-proxies to the host process on `127.0.0.1:8888`

## Components

### FastAPI Application

**Location**: `api/main.py` (the entire app; `api/extract-openapi.py` dumps the OpenAPI spec).

**Key Features**:
- Webhook-driven project redeploys (delegates to `itsup apply`)
- Project listing
- Single-API-key authentication

**Endpoints** (actual, from `api/main.py`):
```
GET /update-upstream/{project}            # Webhook: triggers `itsup apply <project>` (auth)
GET /update-upstream/{project}/{service}  # Same, scoped to one service (auth)
GET /projects                             # List all projects (auth)
GET /redirect?url=...                     # 307 redirect; only message:// / imessage:// schemes
```

The special project name `itsUP` on `/update-upstream/itsUP` updates itsUP itself: in production it `git fetch`/`reset --hard origin/main`, redeploys the DNS and proxy stacks, runs `itsup apply` for all projects, and restarts the API.

There is **no `/health` endpoint**.

### Process Management

**Start**: `bin/start-api.sh` — kills any process already on `:8888` (`fuser 8888/tcp`), then launches `python api/main.py` in the background with output to `logs/api.log`. In the orchestrated stack the API is started by `itsup run`; on a persistent host the systemd bringup installed by `bin/install-bringup.sh` keeps it running.

**Stop**: Kill the Python process on `:8888`, or stop the bringup service.

**Logs**: `logs/api.log` (rotated via logrotate)

## Deployment

### Manual Start
```bash
# From project root
bin/start-api.sh
```

### Systemd Service (illustrative)

The real host bringup is installed by `bin/install-bringup.sh` (which manages itsUP startup/apply/backup/healthcheck units). The unit below is an illustrative standalone example only:

Create `/etc/systemd/system/itsup-api.service`:

```ini
[Unit]
Description=itsUP Infrastructure API
After=network.target docker.service

[Service]
Type=simple
User=youruser
WorkingDirectory=/home/youruser/srv
ExecStart=/home/youruser/srv/bin/start-api.sh
Restart=always
RestartSec=10
StandardOutput=append:/home/youruser/srv/logs/api.log
StandardError=append:/home/youruser/srv/logs/api.log

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

Loaded from `secrets/itsup.txt` (or `secrets/itsup.enc.txt`). The API requires a single key:
```bash
# Required: the API key all authenticated endpoints check against
API_KEY=...
```
`lib/auth.py` loads `API_KEY` at import time and fails fast if it is missing.

### Environment Variables

The API inherits environment from:
1. Shell environment (from `bin/start-api.sh`)
2. `secrets/itsup.txt` (loaded via `lib/data.py:get_env_with_secrets()`)
3. `.env` file (if present)

## Logging

### API Logs

**File**: `logs/api.log`

**Format**: Configured by `api-log.conf.yaml` — `%(asctime)s.%(msecs)03dZ %(levelname)-8s %(message)s`. (Uvicorn's access logger is configured to write to `logs/access.log`, the same file Traefik uses.)

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

The API uses a single shared key (`API_KEY` from secrets). `lib/auth.py:verify_apikey` accepts it from any of:
- `?apikey=...` query parameter
- `X-API-KEY` request header
- `Authorization: Bearer ...`

Any other value returns `401 Unauthorized`. There is no session auth, no admin/operator/viewer RBAC, and no per-user attribution — it is a single-key model.

### Network Security

- **Bind Address**: `0.0.0.0:8888` (isolation relies on Traefik/firewall, not on a loopback bind)
- **External Access**: Via Traefik reverse proxy
- **TLS**: Terminated at Traefik (Let's Encrypt certificates)
- **Rate Limiting**: Configured via Traefik middleware if desired

### Input Validation

The `/redirect` endpoint only permits `message://` and `imessage://` URL schemes and rejects URLs containing whitespace. Project/service names passed to `/update-upstream/{project}` are validated against the known project list before any `itsup apply` runs.

## Monitoring

### Health Checks

There is **no `GET /health` endpoint**. Liveness is observed by checking the process on `:8888` and tailing `logs/api.log`. A historical Traefik health-check example (no longer applicable) read:

```yaml
# (example only — the API has no /health route)
http:
  services:
    itsup-api:
      loadBalancer:
        servers:
          - url: "http://127.0.0.1:8888"
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
netstat -tlnp | grep :8888
# Should show the Python process listening on 0.0.0.0:8888
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
cat projects/itsup/itsup-project.yml
# Verify domain, port, host IP correct
```

**Test direct access** (requires the API key):
```bash
curl "http://localhost:8888/projects?apikey=$API_KEY"
```

**Test via Traefik**:
```bash
curl -H "Host: itsup.srv.instrukt.ai" -H "X-API-KEY: $API_KEY" http://localhost:8080/projects
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
/home/youruser/srv/logs/api.log {
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

# Run API directly (start-api.sh uses: PYTHONPATH=. python api/main.py)
PYTHONPATH=. python api/main.py
```

### Code Structure

```
api/
├── main.py             # The entire FastAPI app: routes, auth wiring, uvicorn entry point
└── extract-openapi.py  # Dumps the OpenAPI spec to openapi.yaml
```

Authentication lives in `lib/auth.py`; route handlers delegate work to `lib/data.py` and `lib/deploy.py`.

### Testing

```bash
# Unit tests (discovered from repo root across lib/, commands/, bin/)
bin/test.sh
```

## Future Improvements

- **WebSocket Support**: Real-time log streaming and status updates
- **Metrics Collection**: Prometheus-compatible metrics endpoint
- **Event Streaming**: Server-sent events for deployment progress
- **Audit Logging**: Track all management operations with user attribution
- **Role-Based Access**: Fine-grained permission system
- **API Documentation**: OpenAPI/Swagger UI for interactive API docs
