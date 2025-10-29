# Logging

itsUP uses a hybrid logging approach: file-based logs for non-containerized services and specific use cases, Docker's native logging for containerized services.

## Log Files

### File-Based Logs (logs/ directory)

Three log files are written to disk and managed by logrotate:

```
logs/
├── access.log      # Traefik access logs (JSON format)
├── api.log         # API server logs
└── monitor.log     # Security monitor logs
```

#### access.log (Traefik)
- **Format**: JSON (one entry per request)
- **Source**: Traefik container writes to `/var/log/traefik/access.log` (mounted to `logs/`)
- **Purpose**: HTTP/HTTPS request logging for CrowdSec analysis and security monitoring
- **Special handling**: Required for CrowdSec to parse and detect threats

#### api.log (API Server)
- **Format**: Custom format `[timestamp] LEVEL > path/to/file.py: message`
- **Source**: Non-containerized Python FastAPI server
- **Purpose**: API server operations, request handling, errors

#### monitor.log (Security Monitor)
- **Format**: Custom format (same as api.log)
- **Source**: Non-containerized Python security monitor process
- **Purpose**: Container security events, threat detections, blocked connections

### Container Logs

All Docker containers use Docker's default `json-file` logging driver:

```bash
# View container logs
docker logs <container-name>
docker compose logs -f <service>

# View via itsup
itsup proxy logs traefik
itsup dns logs
```

**Configuration**:
- Driver: `json-file`
- Max size: 10MB per file
- Max files: 3 (30MB total per container)
- Location: `/var/lib/docker/containers/{container-id}/*.log`

Container logs are rotated automatically by Docker and lost when containers are removed. This is acceptable for:
- Debugging recent issues (2-3 days retention)
- Real-time monitoring via `docker logs -f`

## Log Rotation

Managed by `/etc/logrotate.d/itsup`:

### Traefik Access Log
```
/home/morriz/srv/logs/access.log {
  size 10M
  rotate 5
  missingok
  notifempty
  compress
  delaycompress
  postrotate
    docker compose -f /home/morriz/srv/proxy/docker-compose.yml exec -T traefik kill -USR1 1 2>/dev/null || true
  endscript
}
```

**How it works:**
1. When `access.log` reaches 10MB, logrotate runs
2. Moves `access.log` → `access.log.1` (and rotates older logs)
3. Sends `USR1` signal to Traefik container
4. Traefik receives signal and reopens log file (creates new `access.log`)
5. No downtime, no log loss

**Why USR1?**
- Official Traefik method for log rotation
- Zero downtime - just reopens file handles
- Safer than `docker kill --signal` (avoids Docker restart policy bugs)

### API & Monitor Logs
```
/home/morriz/srv/logs/api.log /home/morriz/srv/logs/monitor.log {
  size 10M
  rotate 5
  missingok
  notifempty
  compress
  delaycompress
  copytruncate
}
```

**How it works:**
1. When log reaches 10MB, logrotate runs
2. **Copies** log file to `.log.1` (not moves)
3. **Truncates** original log file to 0 bytes
4. Python process keeps writing to same file handle (now empty)

**Why copytruncate?**
- Python `FileHandler` doesn't support signal-based reopening
- Alternative would be restarting processes (causes downtime)
- Brief log loss during copy is acceptable (milliseconds)
- No code changes needed

### Rotation Settings

Common settings for all logs:
- `size 10M` - Rotate when log reaches 10MB
- `rotate 5` - Keep 5 rotated copies (50MB total per log)
- `compress` - Gzip old logs (.log.1.gz, .log.2.gz, etc.)
- `delaycompress` - Don't compress most recent rotation (in case still being written)
- `missingok` - Don't error if log doesn't exist
- `notifempty` - Don't rotate empty logs

## Viewing Logs

### Using itsup logs command

```bash
# Follow all file-based logs
itsup logs

# Follow specific logs
itsup logs access
itsup logs api monitor

# Show last N lines (default 100)
itsup logs access -n 50
```

**Features:**
- Automatically formats JSON logs (access.log) for readability
- Clean output without filename separators
- Follows new entries in real-time
- Tab completion for log names

### Direct file access

```bash
# Current logs
tail -f logs/access.log
tail -f logs/api.log logs/monitor.log

# Rotated logs (compressed)
zcat logs/access.log.1.gz
zgrep "error" logs/api.log.*.gz

# Search all rotated logs
zgrep -h "192.168.1.74" logs/access.log.*.gz
```

### Container logs

```bash
# Via docker compose
cd proxy && docker compose logs -f traefik
cd dns && docker compose logs -f

# Via itsup (planned enhancement)
itsup proxy logs traefik
itsup svc <project> logs <service>
```

## Log Format

### Access Log (JSON)
```json
{
  "ClientAddr": "192.168.1.100:54321",
  "DownstreamStatus": 200,
  "Duration": 12345678,
  "RequestHost": "example.com",
  "RequestMethod": "GET",
  "RequestPath": "/api/users",
  "RouterName": "my-app@docker",
  "ServiceName": "my-app@docker",
  "TLSVersion": "1.3",
  "level": "info",
  "time": "2025-10-28T12:34:56Z"
}
```

Formatted by `bin/format-logs.py`:
```
2025-10-28T12:34:56Z INFO 192.168.1.100 "GET example.com/api/users" → my-app 200 12ms
```

### API/Monitor Log Format
```
2025-10-28 12:34:56.789 INFO > api/main.py: Starting API server on :8888
2025-10-28 12:34:57.123 ERROR > monitor/core.py: Connection blocked: 172.20.0.5:443
```

Format: `[timestamp] LEVEL > relative/path.py: message`

## Log Analysis

### Current Capabilities

**CrowdSec** (automatic):
- Parses `access.log` for threat patterns
- Detects brute force, SQL injection, XSS, etc.
- Auto-bans malicious IPs

**Manual analysis**:
```bash
# Find errors in API logs
grep ERROR logs/api.log

# Find blocked connections
grep "blocked" logs/monitor.log

# Analyze traffic patterns
itsup logs access | grep "404"

# Search rotated logs
zgrep -h "192.168.1.74" logs/access.log.*.gz | bin/format-logs.py
```

### Future: Loki Integration (Recommended)

For real insights from logs, consider adding Loki + Grafana:

**Benefits:**
- Query logs with LogQL: `{service="traefik"} |= "error" | json | status >= 500`
- Visual dashboards: request rates, error rates, top IPs
- Alerts: notify when error rate spikes
- Correlation: see all logs from a time range across all services
- Historical analysis: query weeks of logs instantly

**Cost:** ~200MB RAM for Loki, minimal CPU

**Not implemented yet** - but the architecture supports it:
- Promtail scrapes Docker logs automatically
- Point Promtail at `logs/*.log` for file-based logs
- Everything centralized in Loki

## Troubleshooting

### Log rotation not working

Check logrotate status:
```bash
# Test rotation (dry-run)
sudo logrotate -d /etc/logrotate.d/itsup

# Force rotation
sudo logrotate -f /etc/logrotate.d/itsup

# Check when last rotated
ls -lh logs/
```

### Traefik still writing to old log after rotation

Symptom: `access.log` is empty, but `access.log.1` keeps growing

Cause: Traefik didn't receive USR1 signal or didn't reopen file

Fix:
```bash
# Check which file Traefik is writing to
docker exec proxy-traefik-1 sh -c 'ls -l /proc/$(pgrep traefik)/fd | grep access.log'

# Should show: access.log (not access.log.1)
# If showing .log.1, restart Traefik:
docker restart proxy-traefik-1
```

### Python logs not appearing after rotation

Symptom: `api.log` or `monitor.log` stops growing after rotation

Cause: `copytruncate` failed or process crashed

Fix:
```bash
# Check if process is running
ps aux | grep -E "(api|monitor)" | grep python

# Check log file permissions
ls -la logs/api.log logs/monitor.log

# Restart service
# API: managed by systemd/supervisor (depends on setup)
# Monitor: itsup monitor restart
```

### Logs directory full

```bash
# Check disk usage
du -sh logs/
du -h logs/*.gz | sort -h

# Remove old rotated logs
gio trash logs/*.log.[3-9]
gio trash logs/*.log.[3-9].gz

# Or increase rotation limit in /etc/logrotate.d/itsup
```

## Best Practices

1. **Don't log secrets** - API keys, passwords, tokens should NEVER be logged
2. **Use appropriate log levels** - DEBUG for development, INFO for production, ERROR for alerts
3. **Keep logs for security/compliance** - Access logs show "who accessed what when"
4. **Monitor log growth** - Set up alerts if logs grow unexpectedly
5. **Test rotation** - Periodically verify logrotate is working
6. **Compress old logs** - Save disk space with gzip

## Related

- [Security Monitoring](monitoring.md) - CrowdSec integration and threat detection
- [Proxy Stack](../stacks/proxy.md) - Traefik configuration
- [API Server](../stacks/api.md) - API logging configuration
