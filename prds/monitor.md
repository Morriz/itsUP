# Container Security Monitor - Product Requirements Document

## Overview

**Purpose**: Detect compromised containers by identifying hardcoded IP connections.

**How**: Correlate DNS queries with outbound TCP connections. If a container connects to an IP it never looked up via DNS, it's using a hardcoded IP (strong malware/C2 indicator).

**Core principle**: Assumption: Legitimate software queries DNS first. Malware uses hardcoded IPs to avoid DNS-based detection.

## Architecture

### Data Sources

1. **DNS Honeypot Logs** (`docker logs dns-honeypot`) - **Required**

   - Captures ALL DNS queries from containers (via 172.30.0.253)
   - Formats:
     - `dnsmasq[N]: reply domain.com is 1.2.3.4` (fresh DNS lookup)
     - `dnsmasq[N]: cached domain.com is 1.2.3.4` (cache hit)
   - Both formats are parsed to build DNS cache (domain → IP mappings)

2. **iptables Kernel Logs** (via `journalctl -k`) - **Required**

   - Captures ALL outbound TCP connections from containers
   - Format: `[CONTAINER-TCP] SRC=172.30.0.x DST=1.2.3.4 SPT=xxxxx DPT=443`
   - Used to detect outbound IP connections

3. **OpenSnitch Database** (`/var/lib/opensnitch/opensnitch.sqlite3`) - **Optional**
   - Only used when `--use-opensnitch` flag is provided
   - Provides historical block data from `0-deny-arpa-53` rule
   - More reliable over time (actively blocking direct IP connections)
   - Used for blacklist inflation and validation (`--cleanup`)

## Functional Requirements

### FR1: Detect Hardcoded IP Connections

The monitor MUST detect when a container connects to an external IP address without first performing a DNS lookup for that IP.

**Detection logic**:

1. Track all DNS queries made by containers (domain → IP mappings)
2. Monitor all outbound TCP connections from containers
3. For each connection: Check if the destination IP was previously resolved via DNS
4. If NO DNS lookup found: Flag as hardcoded IP connection
5. Report which container made the connection and to which IP

**Exclusions**:

- Private/internal IPs (10.x, 172.16-31.x, 192.168.x, 127.x)
- Whitelisted IPs (user-approved)

### FR2: Historical Analysis

On startup, the monitor MUST:

1. **DNS Cache Pre-warming**: Load 48 hours of DNS honeypot logs to build comprehensive DNS cache
   - Wider window than connection scanning to prevent false positives
   - Safe operation - more DNS data = fewer false positives
2. **Connection Scanning**: Resume from last processed timestamp (from `logs/monitor.log`)
   - If no prior run: Process all available historical connection data
   - Only scans connections since last run to avoid duplicate alerts
3. Correlate scanned connections with pre-warmed DNS cache
4. Detect any hardcoded IP connections that occurred while monitor was offline
5. Report all findings before entering real-time mode

**Purpose**: Don't miss suspicious activity between restarts. DNS cache uses wider window to ensure legitimate connections are not flagged as hardcoded IPs.

### FR3: Real-Time Monitoring

The monitor MUST continuously:

1. Watch for new DNS queries
2. Watch for new outbound connections
3. Correlate in real-time
4. Alert immediately on hardcoded IP detection

### FR4: Blacklist Management

The monitor MUST:

- Maintain a persistent blacklist of detected malicious IPs
- Add newly detected IPs to blacklist
- Support user whitelist for false positives
- Block blacklisted IPs via iptables by default (disable with `--report-only` flag)

**Modes**:

- **Default**: Detection + iptables DROP rules (blocking enabled)
- **--report-only**: Detection-only (log but don't block)
- **--skip-sync**: Memory-only (no file persistence, for analysis)

### FR6: OpenSnitch Cross-Reference (Optional)

**Architecture principle**: The monitor and OpenSnitch are **independent, standalone solutions** that can cross-reference each other for validation.

When `--use-opensnitch` flag is provided, the monitor MUST:

- Load OpenSnitch's blocked IPs from `0-deny-arpa-53` rule into memory
- **DO NOT sync or modify our blacklist** based on OpenSnitch data
- When our monitor detects a hardcoded IP, cross-reference with OpenSnitch:
  - **IP in OpenSnitch blocks**: Log "✅ CONFIRMED by OpenSnitch" (high confidence threat)
  - **IP NOT in OpenSnitch blocks**: Log "⚠️ NOT in OpenSnitch (possible false positive)" (needs review)

**Rationale**:

- Our monitor and OpenSnitch work independently
- OpenSnitch provides **validation**, not data source
- If our monitor detects something that OpenSnitch also blocked → high confidence
- If our monitor detects something that OpenSnitch did NOT block → warrants extra scrutiny
- Keeps both systems decoupled and testable

**Without flag**: Monitor operates independently using only DNS correlation (no cross-reference).

### FR7: Blacklist Cleanup and Validation

The `--cleanup` flag MUST:

- Load both our blacklist AND OpenSnitch's blocked IPs
- Compare the two datasets:
  - **In our blacklist, IN OpenSnitch**: Confirmed threats (keep in blacklist)
  - **In our blacklist, NOT in OpenSnitch**: Potential false positives (prompt to whitelist)
- Display potential false positives with their associated domains (if any)
- Prompt user to move false positives to whitelist
- Update both blacklist and whitelist files based on user selection

**Purpose**: Retroactively validate our monitor's detections against OpenSnitch's confirmed blocks. Helps refine blacklist accuracy over time.

**Requirement**: Requires OpenSnitch database access

### FR5: Container Identification

The monitor MUST identify which container made each suspicious connection by name (not just IP address).

## Modes of Operation

| Mode                | Flag               | Blacklist File | iptables Blocking | OpenSnitch      | Use Case                                                                 |
| ------------------- | ------------------ | -------------- | ----------------- | --------------- | ------------------------------------------------------------------------ |
| **Block** (default) | (none)             | Read/Write     | Yes               | No              | Active defense (standalone)                                              |
| Detection Only      | `--report-only`    | Read/Write     | No                | No              | Production monitoring (standalone)                                       |
| OpenSnitch Mode     | `--use-opensnitch` | Read/Write     | Yes               | Cross-reference | Active defense + OpenSnitch validation                                   |
| Memory-Only         | `--skip-sync`      | None           | No                | No              | Testing/analysis                                                         |
| Cleanup Mode        | `--cleanup`        | Read/Write     | N/A               | Required        | Validate blacklist against OpenSnitch, move false positives to whitelist |

**Note**: Flags can be combined (e.g., `--report-only --use-opensnitch` for detection-only with OpenSnitch validation).

## Integration Points

### OpenSnitch Integration (when `--use-opensnitch` is enabled)

**Startup (initial load)**:

1. Query OpenSnitch database for all IPs blocked by `0-deny-arpa-53` rule
2. Load these IPs into in-memory set: `_opensnitch_blocked_ips`
3. This set is used for cross-reference validation only

**Real-time Monitoring**:

1. Monitor OpenSnitch database for new blocks (via `monitor_opensnitch()` thread)
2. Add newly blocked IPs to `_opensnitch_blocked_ips` set
3. Keeps validation set current without requiring monitor restart

**Real-time Detection**:
When our monitor detects a hardcoded IP connection:

1. Add IP to our blacklist (standard detection flow)
2. Check if IP exists in `_opensnitch_blocked_ips` set
3. Log confidence level:
   ```
   ✅ CONFIRMED by OpenSnitch - high confidence threat
   ⚠️  NOT in OpenSnitch (needs review) - possible false positive
   ```

**Cleanup Mode (`--cleanup` flag)**:

1. Load our blacklist IPs
2. Load OpenSnitch blocked IPs
3. Find IPs in our blacklist but NOT in OpenSnitch
4. Show these as potential false positives for user review
5. User decides to keep or move to whitelist

**Key principle**: OpenSnitch data is **validation signal only**, never modifies our blacklist automatically.

## Design Decisions

### DD1: OpenSnitch as Independent Validation Layer

**Decision**: OpenSnitch integration is optional via `--use-opensnitch` flag and provides **cross-reference validation only** (no data synchronization)

**Rationale**:

- Monitor and OpenSnitch are **independent, standalone solutions**
- Monitor uses DNS correlation to detect hardcoded IPs
- OpenSnitch uses eBPF to block reverse DNS queries (0-deny-arpa-53 rule)
- When enabled: OpenSnitch data is loaded into memory for **cross-reference** only
- Our blacklist is **never modified** by OpenSnitch data
- Cross-referencing provides confidence signals:
  - Detection confirmed by both systems → high confidence threat
  - Detection by our monitor only → needs review (possible edge case or false positive)
- Keeps systems decoupled and independently testable
- User can run either system alone or both for validation

### DD2: Hardcoded IP Policy

**Decision**: Flag ALL hardcoded IPs as suspicious

**Rationale**: Modern software uses DNS for flexibility. Hardcoded IPs indicate immature/insecure design or malware. Users can whitelist edge cases.

## Implementation Notes

**Data Storage**:

- DNS correlation: Persistent JSON registry (`data/dns-registry.json`) + in-memory cache
  - Registry survives restarts, preserves unlimited DNS history
  - First run: Bootstrap from 48h of docker logs
  - Subsequent runs: Load full registry history
- Blacklist: Persistent file (`data/blacklist/blacklist-outbound-ips.txt`)
- Whitelist: Persistent file (`data/whitelist/whitelist-outbound-ips.txt`)

**Traffic Direction Detection**:

- Source port filtering used to distinguish outbound vs inbound traffic
- Outbound connections: ephemeral ports (typically 32768-60999)
- Server responses: privileged/service ports (80, 443, etc.)
- Only flag connections with source port > 1024 to exclude server response traffic

**Timestamp Accuracy**:

- Kernel logs parsed with `--output=short-iso-precise` for microsecond precision
- Grace period measured from **actual event timestamp** (from log), not stream arrival time
- Eliminates false positives from variable log buffering delays
- Stream delays >2s logged as DEBUG warnings for diagnostics

**Typical Workflow**:

1. Run monitor in detection mode first: `bin/monitor.py --report-only`
2. Periodically validate with OpenSnitch: `bin/monitor.py --cleanup`
3. Review false positives, move to whitelist
4. Enable blocking when confident: `bin/monitor.py --use-opensnitch`
