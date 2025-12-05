# Container Security Monitor

## Overview

Detects compromised containers by identifying hardcoded IP connections (malware indicator) through DNS correlation analysis.

## Core Detection Logic

**Hardcoded IP Detection:**

- Monitor all outbound TCP connections from Docker containers
- Check if destination IP was previously resolved via DNS
- If NO DNS history exists → Flag as hardcoded IP (malware indicator)
- If DNS history exists → Connection is legitimate

## Architecture

### Components

1. **DNS Honeypot Monitor** - Captures DNS queries from all containers via dnsmasq logs
2. **DNS Registry** - Persistent JSON storage of IP → domain mappings (survives restarts)
3. **iptables Monitor** - Captures outbound TCP connections via kernel logs
4. **Container Mapping** - Tracks container IP → name mappings via Docker API
5. **Docker Events Listener** - Real-time updates to container mappings on start/stop/restart
6. **OpenSnitch Integration** (optional) - Cross-reference with eBPF application firewall
7. **IP Lists** - Blacklist and whitelist management with auto-reload
8. **Grace Period** - 3-second delay before checking connections (uses actual event timestamps, not stream arrival time)

### Data Flow

```
Container → DNS Query → dnsmasq → Honeypot Logs → DNS Cache → DNS Registry (persisted)
Container → Direct TCP → iptables → Kernel Logs (µs timestamps) → Queue (3s grace) → Connection Analysis
Connection Analysis + DNS Cache → Threat Detection → Alert/Block

Note: Grace period uses actual event timestamps from kernel logs (microsecond precision),
not stream arrival time. This ensures accurate measurement regardless of log buffering delays.
```

## Important Operational Notes

### ✅ No Container Restart Required

**The monitor now uses a persistent DNS registry** (`data/dns-registry.json`) that:

- Survives monitor restarts
- Preserves all historical DNS resolutions
- Eliminates false positives from application-level DNS caching
- No need to restart containers when starting the monitor

**How it works:**

- DNS registry persists all IP → domain mappings indefinitely
- On startup, loads existing registry (could contain days/weeks of data)
- Real-time DNS queries update the registry and save to disk
- Connections are checked against the full registry history

**First-time setup only:** On very first run, the registry is bootstrapped from 48 hours of docker logs.

## Prerequisites

### OpenSnitch Setup (Optional but Recommended)

For enhanced detection confidence, install OpenSnitch application firewall and configure ARPA blocking rules:

1. **Install OpenSnitch** - Follow instructions at https://github.com/evilsocket/opensnitch
2. **Deploy OpenSnitch rules** - See [../opensnitch/README.md](../opensnitch/README.md) for detailed installation instructions

The OpenSnitch integration provides:

- Higher confidence threat detection via cross-reference
- Cleanup mode - reviews existing blacklist entries to identify and remove false positives

**The monitor works with OR without OpenSnitch** - use the `--use-opensnitch` flag to enable it.

## Usage

### Start Monitor

```bash
# Basic mode (detect and block by default)
make monitor-start

# With OpenSnitch cross-reference
make monitor-start FLAGS="--use-opensnitch"

# Detection only (no blocking)
make monitor-start FLAGS="--report-only"

# Detection only with OpenSnitch
make monitor-start FLAGS="--report-only --use-opensnitch"

# Memory-only mode (no file persistence)
make monitor-start FLAGS="--skip-sync"
```

### Stop Monitor

```bash
make monitor-stop
```

### View Logs

```bash
tail -f logs/monitor.log
```

### Manage IP Lists

```bash
# Add to whitelist
echo "1.2.3.4" >> data/whitelist/whitelist-outbound-ips.txt

# Remove from blacklist
sed -i '/1.2.3.4/d' data/blacklist/blacklist-outbound-ips.txt

# Monitor auto-reloads files every 5 seconds
```

### Clear iptables Rules

```bash
itsup monitor clear-iptables

# Or via make:
make monitor-clear-iptables
```

## Configuration

See `monitor/constants.py` for configuration values:

- `LOG_FILE`: Monitor log file location
- `BLACKLIST_FILE`: Blacklist file path
- `WHITELIST_FILE`: Whitelist file path
- `DNS_REGISTRY_FILE`: Persistent DNS registry JSON file (`data/dns-registry.json`)
- `DNS_CACHE_WINDOW_HOURS`: Hours of DNS logs for initial bootstrap (48h default)
- `CONNECTION_DEDUP_WINDOW`: Connection deduplication window (60s default)
- `CONNECTION_GRACE_PERIOD`: Grace period before checking connections (3s default)
- `LOG_LEVEL`: "TRACE", "DEBUG", or "INFO" (from `.env` file)

## Network Architecture

### Monitored Networks

The monitor tracks outbound connections from **all Docker networks** in the `172.0.0.0/8` CIDR range:

- **Project Networks**: `172.18.x.x`, `172.25.x.x`, etc. (per-project isolation)
- **Proxynet**: `172.30.0.0/16` (shared ingress network for Traefik)

### Routing Behavior

Containers use their **primary/first network** for outbound connections:

- Containers with project network → use project IP (e.g., `172.25.0.3`)
- Containers with ONLY proxynet → use proxynet IP (e.g., `172.30.0.27`)

The monitor maps **all IPs** for each container to ensure correct name resolution regardless of which IP appears in logs.

### DNS Flow

1. Container queries DNS → Docker embedded DNS (`127.0.0.11`)
2. Docker DNS → Host DNS (`127.0.0.1`)
3. Host DNS → dnsmasq honeypot
4. Monitor captures dnsmasq logs

## False Positive Handling

### Common Causes

1. **External DNS** - Apps hardcoded to use `8.8.8.8` (rare in Docker)
2. **IPv6 Responses** - We only track IPv4
3. **CDN/Load Balancer IPs** - Legitimate services using Cloudflare, etc.

### Solutions

1. **Persistent Registry** - Automatically prevents most false positives (no container restart needed!)
2. **Grace Period** - 2-second delay allows DNS logs to arrive before checking
3. **Whitelist known CDN ranges** (Cloudflare, Fastly, etc.)
4. **Review OpenSnitch cross-reference** - "needs review" flags may be false positives
5. **Check container logs** - Verify what service the app is connecting to

### Architecture Improvements

The monitor now includes key features that eliminate most false positives:

1. **Persistent DNS Registry**: Survives restarts, preserves all historical DNS data
2. **Actual Event Timestamps**: Parses microsecond-precision timestamps from kernel logs to measure real event age (not stream arrival time)
3. **Grace Period**: Delays connection analysis by 3 seconds based on actual event time to handle docker logs buffering
4. **Stream Delay Detection**: Logs warnings when log stream buffering exceeds 2 seconds (helps diagnose timing issues)

## Testing

```bash
# Run all tests
python3 -m unittest discover monitor -v

# Run specific test file
python3 -m unittest monitor.test_core -v
```

### Test Coverage

- DNS correlation detection (core feature)
- OpenSnitch cross-reference
- Whitelist protection
- Compromise deduplication
- Timestamp resumption
- DNS regex parsing
- Docker events integration

## Logging Format

```
[TIMESTAMP] LEVEL: EMOJI MESSAGE

Log Levels:
- TRACE: DNS honeypot queries (very verbose)
- DEBUG: Detailed DNS mappings for multi-domain IPs
- INFO: Connection analysis results (default)
- WARN: Hardcoded IP detections
- ERROR: System errors

Emojis:
🍯  DNS query captured (TRACE)
🔍  Connection analyzed (INFO)
  ↳ DNS mappings: ... (DEBUG - shows all domains for an IP)
🚨  ALERT: Hardcoded IP detected (WARN)
➕  IP added to blacklist
🚫  IP blocked in iptables
💾  DNS registry saved (DEBUG)
✅  Confirmation/success
⚠️  Warning/needs review
🔄  Auto-reload/update
📋  Status/info
🐳  Docker event (start/stop)
```

## Security Considerations

### iptables Rules Persistence

- DROP rules remain active after monitor stops
- Must manually clear with `make monitor-clear-iptables`
- Prevents accidental exposure when monitor restarts

### Whitelist Priority

- Whitelisted IPs **never** get blacklisted
- Whitelist changes auto-remove IPs from blacklist
- Review whitelist carefully

### OpenSnitch Database

- Database is **read-only** for SELECT queries
- **NEVER** delete or modify `/var/lib/opensnitch/opensnitch.sqlite3`
- Historical blocks are critical for forensics

## Performance

- **CPU**: ~0.5% (5 daemon threads)
- **Memory**: ~30-40 MB
- **Disk I/O**: Minimal (log tailing only)
- **Network**: None (local monitoring only)

## Limitations

1. **IPv4 Only** - IPv6 addresses ignored
2. **TCP Only** - UDP connections not monitored (except DNS)
3. **Docker Networks Only** - Host networking not monitored
4. **DNS Dependency** - Requires DNS queries through honeypot

## Future Enhancements

- [ ] UDP connection monitoring
- [ ] IPv6 support
- [ ] Machine learning for anomaly detection
- [ ] Integration with threat intelligence feeds
- [ ] Web dashboard for monitoring
- [ ] DNS registry expiration/rotation (currently unlimited history)
