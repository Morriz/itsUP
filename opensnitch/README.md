# OpenSnitch Rules

This directory contains OpenSnitch application firewall rules used by the container security monitoring system.

## Rules

### 0-whitelist-arpa-53.json

**Purpose**: Allow reverse DNS lookups for whitelisted IPs.

**How it works**:

- Matches reverse DNS queries (`*.in-addr.arpa`)
- Checks if the queried IP is in the whitelist directory (`data/whitelist/`)
- Allows the query if IP is whitelisted
- Uses `precedence: true` prefix to ensure it's processed FIRST

**Why this matters**:
Legitimate services (GitHub, CrowdSec, npm registries) use CDN/load balancers with rotating IPs. When these services redirect to backend IPs, OpenSnitch would normally block the reverse DNS lookup. This rule creates an exception for known-good services.

**Whitelist management**:

- Add IPs to `data/whitelist/whitelist-outbound-ips.txt`
- One IP per line, comments allowed with `#`
- Changes take effect immediately (OpenSnitch monitors the file)

### 0-deny-arpa-53.json

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
5. Our monitor (`bin/monitor.py`) sees the blocked query
6. Monitor checks: did any container do forward DNS for this IP?
7. If NO forward DNS found → hardcoded IP → malware → blacklist IP

## Installation

```bash
sudo cp opensnitch/*.json /etc/opensnitchd/rules/

# Step 3: Restart OpenSnitch to load all rules
sudo systemctl restart opensnitchd

# Step 4: Verify rules are loaded
sudo journalctl -u opensnitch --since "10 seconds ago" --no-pager | grep -i "loading rules"
```

## Optional Usage

The monitoring system (`bin/monitor.py`) works with **OR** without OpenSnitch:

- **Default**: Does iptables/journalctl logs + DNS honeypot analysis and blacklists IPs not having previous DNS resolution attempt
- **With OpenSnitch**: Uses OpenSnitch database for extra confidence score.

## Verification

After installing the rules, test it works:

```bash
# Check OpenSnitch is blocking reverse DNS
sudo journalctl -u opensnitchd -f | grep "0-deny-arpa-53"

# Run the monitor and watch for ARPA blocks
sudo python3 bin/monitor.py
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
      { "operand": "process.path", "data": "/path/to/binary" },
      { "operand": "dest.port", "data": "53" },
      { "operand": "dest.host", "data": "regex", "type": "regexp" }
    ]
  }
}
```

All conditions in the list must match (AND logic).

## See Also

- [Security Documentation](../docs/security.md) - Full explanation of the detection system
- [Monitor Script](../bin/monitor.py) - Real-time correlation engine
