# OpenSnitch Rules

This directory contains OpenSnitch application firewall rules used by the container security monitoring system.

## Rules

### deny-always-arpa-53.json

**Purpose**: Block reverse DNS lookups (ARPA queries) from Docker daemon.

**How it works**:
- Intercepts DNS queries from `/usr/bin/dockerd` to port 53
- Blocks queries matching pattern `*.in-addr.arpa` (reverse DNS)
- Prevents containers from performing reverse DNS on hardcoded IPs

**Why this matters**:
When a container uses a hardcoded IP address (common malware behavior), the Docker daemon attempts to perform reverse DNS to resolve the IP to a hostname. By blocking these attempts, we can detect malicious hardcoded IP connections.

**Detection flow**:
1. Container tries to connect to hardcoded IP (e.g., 45.148.10.89)
2. Docker daemon attempts reverse DNS: `89.10.148.45.in-addr.arpa`
3. OpenSnitch blocks the query (this rule)
4. Our monitor (`bin/docker_monitor.py`) sees the blocked query
5. Monitor checks: did any container do forward DNS for this IP?
6. If NO forward DNS found → hardcoded IP → malware → blacklist IP

## Installation

```bash
# Copy rule to OpenSnitch directory
sudo cp opensnitch/deny-always-arpa-53.json /etc/opensnitchd/rules/

# Restart OpenSnitch to load the rule
sudo systemctl restart opensnitchd

# Verify rule is loaded
sudo journalctl -u opensnitchd -f
```

## Optional Usage

The monitoring system (`bin/docker_monitor.py`) works with **OR** without OpenSnitch:

- **With OpenSnitch**: Uses OpenSnitch database as primary source of truth for blocked IPs (highest confidence)
- **Without OpenSnitch**: Falls back to iptables/journalctl logs + DNS honeypot analysis

OpenSnitch provides:
- Persistent database of blocked connections (SQLite)
- More reliable than volatile DNS logs
- Better cleanup accuracy (`--cleanup` mode)

## Verification

After installing the rule, test it works:

```bash
# Check OpenSnitch is blocking reverse DNS
sudo journalctl -u opensnitchd -f | grep "deny-always-arpa-53"

# Run the monitor and watch for ARPA blocks
sudo python3 bin/docker_monitor.py
```

You should see logs like:
```
📋 Host reverse DNS for 45.148.10.89 - NO container forward query (HARDCODED IP - MALWARE!) 🚨
➕ Added 45.148.10.89 to blacklist
```

## Rule Format

OpenSnitch rules are JSON files with this structure:

```json
{
  "name": "rule-name",
  "action": "deny|allow",
  "duration": "always|once|until-restart",
  "operator": {
    "type": "list",
    "list": [
      {"operand": "process.path", "data": "/path/to/binary"},
      {"operand": "dest.port", "data": "53"},
      {"operand": "dest.host", "data": "regex", "type": "regexp"}
    ]
  }
}
```

All conditions in the list must match (AND logic).

## See Also

- [Security Documentation](../docs/security.md) - Full explanation of the detection system
- [Monitor Script](../bin/docker_monitor.py) - Real-time correlation engine
