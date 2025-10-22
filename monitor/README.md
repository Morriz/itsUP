# Container Security Monitor - Product Requirements Document

## Overview

Container security monitor that detects compromised containers by identifying hardcoded IP connections (malware indicator) through DNS correlation analysis.

## Core Detection Logic

**Hardcoded IP Detection:**
- Monitor all outbound TCP connections from Docker containers
- Check if destination IP was previously resolved via DNS
- If NO DNS history exists → Flag as hardcoded IP (malware indicator)
- If DNS history exists → Connection is legitimate

## Architecture

### Components

1. **DNS Honeypot Monitor** - Captures DNS queries from all containers via dnsmasq logs
2. **iptables Monitor** - Captures outbound TCP connections via kernel logs
3. **Container Mapping** - Tracks container IP → name mappings via Docker API
4. **Docker Events Listener** - Real-time updates to container mappings on start/stop/restart
5. **OpenSnitch Integration** (optional) - Cross-reference with eBPF application firewall
6. **IP Lists** - Blacklist and whitelist management with auto-reload

### Data Flow

```
Container → DNS Query → dnsmasq → Honeypot Logs → DNS Cache
Container → Direct TCP → iptables → Kernel Logs → Connection Analysis
Connection Analysis + DNS Cache → Threat Detection → Alert/Block
```

## Features

### FR1: DNS Correlation Detection
- Monitor dnsmasq logs for DNS replies/cached responses (IPv4 only)
- Build DNS cache: `{ip: [(domain, timestamp), ...]}`
- Correlate outbound connections with DNS cache
- Flag connections without DNS history as threats

### FR2: Timestamp Resumption
- Track last processed timestamp in monitor log
- Resume journalctl scanning from last run (no duplicate analysis)
- Handle first-run scenario (no previous timestamp)

### FR3: Historical Analysis
- Pre-warm DNS cache with 48 hours of logs on startup
- Scan connection logs from last processed timestamp
- Detect past threats that occurred while monitor was offline

### FR4: Real-Time Monitoring
- Monitor DNS queries in real-time
- Monitor outbound TCP connections via journalctl -f
- 0.5s polling interval for responsive detection

### FR5: Container Identification
- Map container IPs to container names
- Handle containers with multiple networks (project + proxynet)
- Real-time updates via Docker events API
- Automatic mapping updates on container start/stop/restart

### FR6: OpenSnitch Cross-Reference (Optional)
- Query OpenSnitch SQLite database for blocked connections
- Cross-reference detections with OpenSnitch blocks
- Label detections as "CONFIRMED" or "needs review"

### FR7: IP List Management
- Blacklist: Detected malicious IPs
- Whitelist: Known-good IPs (never blocked)
- Auto-reload on file changes
- Persistent storage with in-memory cache

### FR8: iptables Blocking (Optional)
- Insert DROP rules for detected IPs
- Rules persist in DOCKER-USER chain
- Manual cleanup required (`--clear-iptables`)

### FR9: Deduplication
- Connection deduplication (60s window)
- Compromise alert deduplication (per container:ip pair)
- DNS cache deduplication (same domain for same IP)

## Important Operational Notes

### ⚠️ Container Restart Requirement

**To avoid false positives from DNS caching:**

When starting the monitor, containers that were already running may have DNS-cached IPs that the monitor never saw resolved. This causes legitimate connections to appear as "hardcoded IPs".

**Solution:** Restart all containers after starting the monitor:

```bash
# Start monitor first
make monitor-start FLAGS="--use-opensnitch --block"

# Then restart containers
docker ps -q | xargs docker restart
```

**Why this works:**
- Clears application-level DNS caches
- Forces fresh DNS queries through the honeypot
- Monitor captures DNS resolutions
- Subsequent connections are correctly identified as legitimate

**Alternative:** Start monitor before starting containers initially (e.g., on system boot).

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
# Basic mode (detect only, no blocking)
make monitor-start

# With OpenSnitch cross-reference
make monitor-start FLAGS="--use-opensnitch"

# With iptables blocking
make monitor-start FLAGS="--block"

# Full protection
make monitor-start FLAGS="--use-opensnitch --block"

# Memory-only mode (no file persistence)
make monitor-start FLAGS="--skip-sync"
```

### Stop Monitor

```bash
make monitor-stop
```

### View Logs

```bash
tail -f /var/log/compromised_container.log
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
make monitor-clear-iptables
```

## Configuration

See `monitor/constants.py` for configuration values:

- `LOG_FILE`: Monitor log file location
- `BLACKLIST_FILE`: Blacklist file path
- `WHITELIST_FILE`: Whitelist file path
- `DNS_CACHE_WINDOW_HOURS`: Hours of DNS logs to pre-warm (48h default)
- `CONNECTION_DEDUP_WINDOW`: Connection deduplication window (60s default)
- `LOG_LEVEL`: "INFO" or "DEBUG"

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

1. **Application DNS Caching** - Apps cache IPs internally
2. **External DNS** - Apps hardcoded to use `8.8.8.8` (rare in Docker)
3. **IPv6 Responses** - We only track IPv4
4. **CDN/Load Balancer IPs** - Legitimate services using Cloudflare, etc.

### Solutions

1. **Restart containers** after monitor startup (clears caches)
2. **Whitelist known CDN ranges** (Cloudflare, Fastly, etc.)
3. **Review OpenSnitch cross-reference** - "needs review" flags may be false positives
4. **Check container logs** - Verify what service the app is connecting to

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
[TIMESTAMP] EMOJI MESSAGE

Emojis:
🍯  DNS query captured
🔍  Connection analyzed
🚨  ALERT: Hardcoded IP detected
➕  IP added to blacklist
🚫  IP blocked in iptables
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
5. **Application Caching** - False positives from cached DNS (mitigated by container restarts)

## Future Enhancements

- [ ] UDP connection monitoring
- [ ] IPv6 support
- [ ] Automatic container restart on monitor startup
- [ ] Machine learning for anomaly detection
- [ ] Integration with threat intelligence feeds
- [ ] Web dashboard for monitoring
- [ ] Automatic Cloudflare/CDN whitelisting
