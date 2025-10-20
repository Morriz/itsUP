# OpenSnitch Rules

This directory contains OpenSnitch application firewall rules used by the container security monitoring system.

## Rules

### 0-whitelist-allow-arpa-53.json

**Purpose**: Allow reverse DNS lookups for whitelisted IPs (must be installed BEFORE deny rule).

**How it works**:
- Matches reverse DNS queries (`*.in-addr.arpa`)
- Checks if the queried IP is in the whitelist directory (`data/whitelist/`)
- Allows the query if IP is whitelisted
- Uses `precedence: true` and `0-` prefix to ensure it's processed FIRST

**Why this matters**:
Legitimate services (GitHub, CrowdSec, npm registries) use CDN/load balancers with rotating IPs. When these services redirect to backend IPs, OpenSnitch would normally block the reverse DNS lookup. This rule creates an exception for known-good services.

**Installation order is critical**:
1. Install `0-whitelist-allow-arpa-53.json` FIRST (the `0-` prefix ensures it runs first)
2. Then install `deny-always-arpa-53.json` as the catch-all blocker

**Whitelist management**:
- Add IPs to `data/whitelist/whitelist-outbound-ips.txt`
- One IP per line, comments allowed with `#`
- Changes take effect immediately (OpenSnitch monitors the file)

### deny-always-arpa-53.json

**Purpose**: Block reverse DNS lookups (ARPA queries) from Docker daemon.

**How it works**:
- Intercepts DNS queries from `/usr/bin/dockerd` to port 53
- Blocks queries matching pattern `*.in-addr.arpa` (reverse DNS)
- Prevents containers from performing reverse DNS on hardcoded IPs
- Only fires if the whitelist rule (above) didn't match

**Why this matters**:
When a container uses a hardcoded IP address (common malware behavior), the Docker daemon attempts to perform reverse DNS to resolve the IP to a hostname. By blocking these attempts, we can detect malicious hardcoded IP connections.

**Detection flow**:
1. Container tries to connect to hardcoded IP (e.g., 45.148.10.89)
2. Docker daemon attempts reverse DNS: `89.10.148.45.in-addr.arpa`
3. OpenSnitch checks whitelist rule first → IP not whitelisted
4. OpenSnitch blocks the query (this deny rule)
5. Our monitor (`bin/docker_monitor.py`) sees the blocked query
6. Monitor checks: did any container do forward DNS for this IP?
7. If NO forward DNS found → hardcoded IP → malware → blacklist IP

## Installation

**IMPORTANT: Install rules in the correct order to ensure whitelist is checked first!**

```bash
# Step 1: Install whitelist rule FIRST
sudo cp opensnitch/0-whitelist-allow-arpa-53.json /etc/opensnitchd/rules/
sudo chmod 644 /etc/opensnitchd/rules/0-whitelist-allow-arpa-53.json

# Step 2: Install deny rule SECOND (catch-all for non-whitelisted IPs)
sudo cp opensnitch/deny-always-arpa-53.json /etc/opensnitchd/rules/
sudo chmod 644 /etc/opensnitchd/rules/deny-always-arpa-53.json

# Step 3: Restart OpenSnitch to load both rules
sudo systemctl restart opensnitchd

# Step 4: Verify rules are loaded
sudo journalctl -u opensnitch --since "10 seconds ago" --no-pager | grep -i "loading rules"
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
