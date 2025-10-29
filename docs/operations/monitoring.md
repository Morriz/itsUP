# Container Security Monitoring

The Container Security Monitor provides real-time protection against malicious container behavior.

## Overview

**Purpose**: Detect and block unauthorized network access from containers using eBPF-based monitoring and OpenSnitch integration.

**Key Features**:
- Real-time connection monitoring with eBPF
- Automated threat detection and blocking
- OpenSnitch integration for DNS-level enforcement
- Threat intelligence reporting
- Blacklist management and cleanup

**Architecture**: Python-based monitor running as host process, integrated with OpenSnitch daemon and iptables.

## How It Works

### Detection Pipeline

1. **eBPF Monitoring**: Captures all container network connections at kernel level
2. **Analysis**: Checks connections against:
   - Whitelist (known-good destinations)
   - Blacklist (blocked destinations)
   - Behavioral patterns (suspicious activity)
3. **Decision**: Allow, block, or report
4. **Enforcement**:
   - Report-only mode: Log only (no blocking)
   - Protection mode: Add to iptables DROP rules
   - OpenSnitch mode: Query OpenSnitch database for DNS-based blocking

### OpenSnitch Integration

**What is OpenSnitch?**: Application-level firewall for Linux with DNS tracking.

**How we use it**:
- OpenSnitch logs all DNS queries and network connections
- Monitor queries OpenSnitch database (`/var/lib/opensnitch/opensnitch.sqlite3`)
- Correlates container IPs with DNS names for better threat intelligence
- Example: "Container made connection to 1.2.3.4 which was resolved from malicious-domain.com"

**Database**: `/var/lib/opensnitch/opensnitch.sqlite3`
- **READ-ONLY**: Monitor only queries (SELECT), never modifies
- Contains permanent security audit log (never delete or move)
- See [Security Database Policy](#security-database-policy)

### Blocking Methods

**iptables Rules**:
```bash
# Blocks container IP from accessing destination
iptables -I DOCKER-USER -s <container_ip> -d <dest_ip> -j DROP

# List current blocks
iptables -L DOCKER-USER -n -v
```

**DNS-Level Blocking** (via OpenSnitch):
- OpenSnitch can block by domain before connection is made
- More effective than IP blocking (works across IP changes)
- Configure via OpenSnitch UI or rules files

## Deployment

### Start/Stop

```bash
itsup monitor start                  # Start with full protection
itsup monitor start --report-only    # Detection only (no blocking)
itsup monitor start --use-opensnitch # Enable OpenSnitch integration
itsup monitor stop                   # Stop monitor
```

### Process Management

**Manual**:
```bash
# Start (protection mode)
python -m monitor.main

# Start (report-only)
python -m monitor.main --report-only

# Stop
pkill -f "python.*monitor.main"
```

**Systemd Service** (Recommended):

Create `/etc/systemd/system/itsup-monitor.service`:

```ini
[Unit]
Description=itsUP Container Security Monitor
After=network.target docker.service opensnitch.service

[Service]
Type=simple
User=root  # Required for eBPF and iptables
WorkingDirectory=/home/morriz/srv
ExecStart=/home/morriz/srv/.venv/bin/python -m monitor.main --use-opensnitch
Restart=always
RestartSec=10
StandardOutput=append:/home/morriz/srv/logs/monitor.log
StandardError=append:/home/morriz/srv/logs/monitor.log

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable itsup-monitor
sudo systemctl start itsup-monitor
sudo systemctl status itsup-monitor
```

### Dependencies

**Required**:
- Python 3.12+ with eBPF libraries
- Docker daemon (for container metadata)
- iptables (for blocking)
- Root privileges (eBPF and iptables require root)

**Optional**:
- OpenSnitch daemon (for DNS-level blocking and tracking)
- OpenSnitch database (`/var/lib/opensnitch/opensnitch.sqlite3`)

## Configuration

### Whitelist

**File**: `config/monitor-whitelist.txt` (or similar)

**Format**: One entry per line
```
# IPs (exact match)
1.2.3.4

# CIDR ranges
10.0.0.0/8
172.16.0.0/12
192.168.0.0/16

# Domains (requires DNS resolution)
*.example.com
trusted-api.com
```

**Purpose**: Known-good destinations that should never be blocked.

### Blacklist

**File**: `config/monitor-blacklist.txt` (or similar)

**Format**: One entry per line with optional metadata
```
# IP:reason:timestamp
1.2.3.4:Malicious connection attempt:2025-01-15T10:30:00
5.6.7.8:C2 server communication:2025-01-15T11:45:00
```

**Auto-Generated**: Monitor adds entries when threats detected.

**Cleanup**: Use `itsup monitor cleanup` to review and remove false positives.

### Modes

**Report-Only Mode** (`--report-only`):
- Detects and logs threats
- No blocking (safe for testing)
- Useful for tuning whitelist/blacklist

**Protection Mode** (default):
- Detects and logs threats
- Blocks via iptables DROP rules
- Active defense

**OpenSnitch Mode** (`--use-opensnitch`):
- All protection mode features
- Plus DNS correlation from OpenSnitch database
- Enhanced threat intelligence reporting

## Logging

### Monitor Logs

**File**: `logs/monitor.log`

**Format**: Structured logging with timestamps, container info, connection details

**Rotation**:
- Method: `copytruncate` (Python process keeps writing)
- Size: 10M per rotation
- Keep: 5 rotations
- Compression: gzip (delayed)

**View**:
```bash
itsup monitor logs            # Tail live (via CLI)
tail -f logs/monitor.log      # Tail directly
grep "BLOCKED" logs/monitor.log  # Search for blocks
```

See [Logging Documentation](logging.md) for details.

### Event Types

```
INFO  | Container started: container_name (172.17.0.5)
WARN  | Suspicious connection: container_name -> 1.2.3.4:443
ERROR | Blocked connection: container_name -> 1.2.3.4:443 (blacklisted)
INFO  | DNS correlation: 1.2.3.4 = malicious-domain.com
```

## Operations

### View Current Blocks

**iptables rules**:
```bash
sudo iptables -L DOCKER-USER -n -v
# Shows blocked IPs with packet/byte counts
```

**Blacklist file**:
```bash
cat config/monitor-blacklist.txt
```

### Cleanup False Positives

```bash
itsup monitor cleanup
```

**Interactive process**:
1. Shows each blacklist entry
2. Prompts to keep or remove
3. Updates blacklist file
4. Removes corresponding iptables rules

### Generate Threat Report

```bash
itsup monitor report
```

**Output**: Comprehensive report including:
- Total connections monitored
- Threats detected and blocked
- Top blocked destinations
- Container-level statistics
- DNS correlations (if OpenSnitch enabled)
- Time-series analysis

**Use Cases**:
- Security audits
- Trend analysis
- Incident investigation
- Compliance reporting

### Manual Blocking

**Block an IP manually**:
```bash
sudo iptables -I DOCKER-USER -s <container_ip> -d <dest_ip> -j DROP
```

**Add to blacklist**:
```bash
echo "1.2.3.4:Manual block:$(date -Iseconds)" >> config/monitor-blacklist.txt
```

### Unblock an IP

**Remove iptables rule**:
```bash
# Find rule number
sudo iptables -L DOCKER-USER -n --line-numbers

# Delete rule by number
sudo iptables -D DOCKER-USER <line_number>
```

**Remove from blacklist**:
```bash
# Edit file or use cleanup command
itsup monitor cleanup
```

## Security Database Policy

### Critical Rules

🚨 **NEVER MODIFY OR MOVE OPENSNITCH DATABASE** 🚨

- **Location**: `/var/lib/opensnitch/opensnitch.sqlite3`
- **Access**: READ-ONLY (SELECT queries only)
- **Purpose**: Permanent security audit log

**Forbidden Operations**:
- ❌ DELETE queries
- ❌ UPDATE queries
- ❌ mv, cp, rm operations on database file
- ❌ Moving or renaming database
- ❌ Modifying database schema

**Why**: Historical block data is critical for:
- Security forensics
- Threat analysis
- Compliance audits
- Incident investigation

**Handling False Positives**:
- Modify whitelist/blacklist files
- Update iptables rules
- NEVER delete database entries

## Troubleshooting

### Monitor Not Starting

**Check privileges**:
```bash
# Monitor requires root for eBPF and iptables
sudo python -m monitor.main
```

**Check eBPF support**:
```bash
# Kernel must support eBPF
uname -r  # Should be 4.x or higher
```

**Check dependencies**:
```bash
# eBPF libraries
pip show bcc  # Or whatever eBPF library is used
```

### High False Positive Rate

**Solution**: Tune whitelist

1. Run in report-only mode for 24-48 hours:
   ```bash
   itsup monitor stop
   itsup monitor start --report-only
   ```

2. Review logs for legitimate traffic:
   ```bash
   grep "BLOCKED" logs/monitor.log | sort | uniq -c
   ```

3. Add legitimate destinations to whitelist:
   ```bash
   echo "legitimate-api.com" >> config/monitor-whitelist.txt
   echo "10.1.2.3" >> config/monitor-whitelist.txt
   ```

4. Restart in protection mode:
   ```bash
   itsup monitor stop
   itsup monitor start
   ```

### OpenSnitch Integration Not Working

**Check OpenSnitch is running**:
```bash
sudo systemctl status opensnitch
```

**Check database exists**:
```bash
ls -lh /var/lib/opensnitch/opensnitch.sqlite3
# Should show file with permissions
```

**Check database access**:
```bash
sudo sqlite3 /var/lib/opensnitch/opensnitch.sqlite3 "SELECT COUNT(*) FROM connections;"
# Should return a number
```

**Check monitor has permissions**:
```bash
# Monitor process must run as root or have database read access
sudo -u root ls -l /var/lib/opensnitch/opensnitch.sqlite3
```

### Blocked Legitimate Traffic

**Immediate fix** (unblock):
```bash
# Find rule
sudo iptables -L DOCKER-USER -n --line-numbers | grep <dest_ip>

# Remove rule
sudo iptables -D DOCKER-USER <line_number>
```

**Permanent fix** (prevent future blocks):
```bash
# Add to whitelist
echo "<dest_ip>" >> config/monitor-whitelist.txt

# Or domain-based
echo "legitimate-domain.com" >> config/monitor-whitelist.txt

# Restart monitor to reload whitelist
itsup monitor stop
itsup monitor start
```

### High Memory Usage

eBPF monitoring can consume memory for large deployments:

**Solution**: Set memory limits in systemd:
```ini
[Service]
MemoryMax=512M
MemoryHigh=400M
```

**Or**: Restart monitor periodically (e.g., daily cron job):
```bash
# Add to crontab
0 3 * * * systemctl restart itsup-monitor
```

## Best Practices

### Initial Deployment

1. **Start with report-only mode** for 1-2 weeks
2. **Review logs daily** to tune whitelist
3. **Test blocking** on non-critical containers first
4. **Enable full protection** after whitelist is stable
5. **Monitor blacklist growth** - high growth indicates tuning needed

### Maintenance

- **Weekly**: Review monitor logs for trends
- **Monthly**: Run cleanup command to remove stale blacklist entries
- **Quarterly**: Generate threat report for security review
- **Yearly**: Full whitelist/blacklist audit

### Integration with Incident Response

1. **Alert on blocks**: Configure log monitoring to alert on BLOCKED events
2. **Investigate immediately**: Use `itsup monitor report` to analyze
3. **Correlate with OpenSnitch**: Check DNS lookups for context
4. **Document in blacklist**: Add detailed reason for each block
5. **Review periodically**: Cleanup command helps identify patterns

## Future Improvements

- **Machine Learning**: Anomaly detection for container behavior
- **Threat Intelligence Feeds**: Auto-update blacklist from public feeds
- **Container Sandboxing**: Automatic isolation for suspicious containers
- **Real-Time Alerts**: Webhook/email notifications for critical blocks
- **Grafana Dashboard**: Real-time visualization of threats and blocks
- **Export to SIEM**: Integration with security information and event management systems
