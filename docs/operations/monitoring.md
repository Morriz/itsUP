# Container Security Monitoring

The Container Security Monitor provides real-time detection of malicious container
behavior by spotting connections to **hardcoded IP addresses** — a common malware
indicator — through DNS-correlation analysis.

## Overview

**Purpose**: Detect compromised containers that connect to hardcoded IPs (skipping
DNS), then blacklist and optionally block those IPs.

**Key Features**:
- DNS-honeypot correlation (no prior DNS lookup ⇒ hardcoded IP ⇒ threat)
- Persistent DNS registry that survives monitor restarts
- Automated blacklisting + kernel-level blocking via iptables `DROP`
- Optional OpenSnitch cross-reference for higher confidence
- Threat-intelligence reporting
- Blacklist/whitelist management with auto-reload

**Architecture**: A non-containerized Python service (`bin/monitor.py` →
`monitor/` package) running as a host process under root. It does **not** use eBPF.

> Source of truth for the detection internals: [`monitor/README.md`](../../monitor/README.md).

## How It Works

### Detection Pipeline (no eBPF)

1. **DNS honeypot** — all container DNS is routed through a logging dnsmasq
   instance (`dns-honeypot` container). The monitor tails its logs
   (`docker logs -f dns-honeypot`), parses `reply/cached <domain> is <ip>` lines,
   and records each IP → domain mapping in an in-memory DNS cache.
2. **DNS registry** — the cache is persisted to `data/dns-registry.json` so it
   survives restarts. On the very first run only, the registry is bootstrapped
   from 48 hours of honeypot logs.
3. **Connection capture** — an iptables `LOG` rule on the `DOCKER-USER` chain
   (source `172.0.0.0/8`, NEW conntrack state) emits `[CONTAINER-TCP]` kernel log
   lines for every new outbound container TCP connection. The monitor tails
   `journalctl -k` to read them.
4. **Correlation** — after a 3-second grace period (to let DNS logs arrive), each
   outbound destination IP is checked:
   - In whitelist → allowed, logged.
   - In blacklist → reported as compromise.
   - Has DNS history → legitimate, logged as `OK`.
   - **No DNS history → hardcoded IP → flagged as a threat**: added to the
     blacklist and, unless in report-only mode, blocked with an iptables `DROP`
     rule.

### Decision / Enforcement

- **Report-only mode** (`--report-only`): detect and log, no blocking.
- **Protection mode** (default): detect, log, and add iptables `DROP` rules.
- **OpenSnitch cross-reference** (`--use-opensnitch`): adds a read-only validation
  layer (see below). It does **not** change what gets blocked.

### OpenSnitch Integration (optional, read-only cross-reference)

**What is OpenSnitch?**: An application-level firewall for Linux. Its own
`0-deny-arpa-53` rule blocks reverse-DNS (`*.in-addr.arpa`) lookups that the Docker
daemon performs on hardcoded destination IPs. See [`opensnitch/README.md`](../../opensnitch/README.md)
and [Security Documentation](../security.md) for the full mechanism.

**How the monitor uses it**:
- The monitor **only reads** the OpenSnitch SQLite database
  (`/var/lib/opensnitch/opensnitch.sqlite3`) — it never asks OpenSnitch to block.
- New blacklist entries are cross-referenced against OpenSnitch's historical ARPA
  blocks and tagged `✅ CONFIRMED by OpenSnitch` or `⚠️ NOT in OpenSnitch (needs review)`.
- `--cleanup` mode uses the OpenSnitch DB as the **primary** source of truth to
  identify false positives in the blacklist (DNS logs are the fallback).

**The monitor works with OR without OpenSnitch** — it is purely additive confidence.

### Blocking Method

The only blocking the monitor performs is iptables `DROP` on the `DOCKER-USER`
chain:

```bash
# Per-IP DROP rule the monitor adds (source = Docker CIDR, dest = blocked IP)
iptables -I DOCKER-USER 1 -s 172.0.0.0/8 -d <dest_ip> -j DROP

# List current blocks
iptables -L DOCKER-USER -n -v
```

DROP rules remain active after the monitor stops. Remove them with
`itsup monitor clear-iptables` (see below).

## Deployment

### Start / Stop (via itsup)

```bash
itsup monitor start                  # Detection + iptables blocking (default)
itsup monitor start --report-only    # Detection only (no blocking)
itsup monitor start --use-opensnitch # Add OpenSnitch cross-reference
itsup monitor start --skip-sync      # Memory-only mode (no file persistence)
itsup monitor stop                   # Stop monitor
itsup monitor logs                   # Tail logs/monitor.log
itsup monitor cleanup                # Review blacklist for false positives
itsup monitor clear-iptables         # Remove monitor's LOG + DROP rules
itsup monitor report                 # Generate threat-intelligence report
```

`itsup monitor start` launches `bin/start-monitor.sh`, which daemonizes
`sudo python3 bin/monitor.py` in the background.

**Note**: When using `itsup run` to start the complete infrastructure stack, the
monitor is started in **report-only** mode for safe operation. To enable active
blocking, stop it and restart with `itsup monitor start`.

### Direct invocation

The monitor must run as root (for iptables and `journalctl -k`):

```bash
sudo python3 bin/monitor.py                       # detection + blocking (default)
sudo python3 bin/monitor.py --report-only         # detection only
sudo python3 bin/monitor.py --use-opensnitch       # blocking + OpenSnitch cross-ref
sudo python3 bin/monitor.py --report-only --use-opensnitch
sudo python3 bin/monitor.py --skip-sync           # memory-only, no file I/O
sudo python3 bin/monitor.py --cleanup             # validate blacklist vs OpenSnitch
sudo python3 bin/monitor.py --clear-iptables      # remove iptables rules
```

Stop a directly-launched monitor:

```bash
sudo pkill -f docker_monitor.py
```

(`docker_monitor.py` is the historical process-name pattern that `start-monitor.sh`
and `itsup monitor stop` match against.)

### Dependencies

**Required**:
- Python 3.11 (the project venv)
- Docker daemon (container metadata + honeypot logs via `docker logs`)
- `journalctl` (reads kernel `[CONTAINER-TCP]` log lines)
- iptables (LOG rule + DROP blocking)
- Root privileges

**Optional**:
- OpenSnitch daemon + database (`/var/lib/opensnitch/opensnitch.sqlite3`) for the
  read-only cross-reference and `--cleanup` validation.

There is **no** eBPF dependency (no `bcc`/BPF libraries). OpenSnitch itself uses
eBPF internally, but the itsUP monitor does not.

## Configuration

Configuration values live in `monitor/constants.py`. Key paths and tunables:

- `BLACKLIST_FILE`: `data/blacklist/blacklist-outbound-ips.txt`
- `WHITELIST_FILE`: `data/whitelist/whitelist-outbound-ips.txt`
- `DNS_REGISTRY_FILE`: `data/dns-registry.json`
- `DNS_CACHE_WINDOW_HOURS`: 48 (first-run registry bootstrap)
- `CONNECTION_GRACE_PERIOD`: 3.0s (delay before correlating a connection)
- `CONNECTION_DEDUP_WINDOW`: 60s
- `LOG_LEVEL`: `TRACE` / `DEBUG` / `INFO` (from `.env`)

### Whitelist

**File**: `data/whitelist/whitelist-outbound-ips.txt`

**Format**: one **bare IPv4 address per line**. `#` comments are allowed (inline or
full-line). **No CIDR ranges, no domains, no wildcards** — the parser only matches
exact IPv4 strings.

```
# Whitelist - IPs that should not be logged or blocked
151.101.206.132   # Fastly CDN (Alpine apk repo)
140.82.121.9      # GitHub
```

**Purpose**: trusted IPs that are hardcoded in trusted containerized apps doing
direct outbound TCP. Ideally this file is empty — hardcoded IPs should be rare.

Whitelisted IPs are **never blacklisted**. When this file changes, the monitor
auto-reloads it (mtime check every ~5s), **auto-removes** any newly whitelisted IPs
from the blacklist, and removes their iptables DROP rules. No restart needed.

### Blacklist

**File**: `data/blacklist/blacklist-outbound-ips.txt`

**Format**: one **bare IPv4 address per line** (`#` comments allowed). There is no
`IP:reason:timestamp` schema — a line like that would be ingested as a malformed
"IP" and never match.

**Auto-generated**: the monitor appends an IP when it detects a hardcoded-IP
connection. The file is also auto-reloaded on change (additions get a DROP rule,
removals get the DROP rule deleted).

**Cleanup**: `itsup monitor cleanup` (interactive) reviews entries against OpenSnitch
(primary) and DNS logs (fallback) and offers to move false positives to the whitelist.

## False Positives

The correlation engine flags any container egress to a **direct IP with no prior
DNS lookup it could observe** as a hardcoded-IP threat. Some legitimate
infrastructure is reached this way and therefore lands in the blacklist as a
false positive — for example:

- GitHub (`140.82.x`)
- Fastly CDN (`151.101.x`)
- GitHub Pages (`185.199.108.x`)
- Quad9 DNS (`9.9.9.10`)

**Remediation — move dedicated-infra IPs to the whitelist**:

```bash
echo "140.82.121.9   # GitHub" >> data/whitelist/whitelist-outbound-ips.txt
```

Whitelisted IPs are never blacklisted, and the monitor auto-removes them from the
blacklist (and from iptables) on the next reload — no restart required.

**Keep cloud-provider ranges blacklisted.** Do **not** blanket-whitelist shared
cloud ranges (AWS / GCP `3.x`, `18.x`, `34.x`, `44.x`, `52.x`, `54.x`): those same
ranges also host real C2 infrastructure. Whitelist only specific dedicated-infra IPs
you have verified; leave cloud-provider IPs on the blacklist and review them
individually.

## Logging

### Monitor Logs

**File**: `logs/monitor.log`

**Format**: `[TIMESTAMP] LEVEL: EMOJI MESSAGE`. Detections are at WARN; connection
analysis at INFO; honeypot queries at TRACE.

**View**:
```bash
itsup monitor logs                       # Tail live (via CLI: tail -f logs/monitor.log)
tail -f logs/monitor.log                 # Tail directly
grep "BLACKLISTED IP" logs/monitor.log   # Compromise hits on known-bad IPs
grep "HARDCODED IP" logs/monitor.log     # New hardcoded-IP detections
```

See [Logging Documentation](logging.md) for rotation details.

### Real log strings

These are the actual messages emitted (emoji-prefixed); there is no `BLOCKED`
token to grep for:

```
🔍 Direct: <container> → <ip>:<port> - OK (DNS: <domain>)        # legitimate
🔍 Direct: <container> → <ip>:<port> - whitelisted               # whitelisted
🔍 Direct: <container> → <ip>:<port> - BLACKLISTED IP 🚨         # hit on known bad IP
🔍 Direct: <container> → <ip>:<port> - NO DNS history (HARDCODED IP - MALWARE?) 🚨
🚨 ALERT: <container> connected to blocked IP <ip> (<evidence>)
➕ detected and blocked (persistent): <ip>                        # added to blacklist
➕ detected and blocked (persistent): <ip> ✅ CONFIRMED by OpenSnitch
➕ detected and blocked (persistent): <ip> ⚠️  NOT in OpenSnitch (needs review)
🚫 Blocked <ip> in iptables
```

## Operations

### View Current Blocks

```bash
sudo iptables -L DOCKER-USER -n -v          # iptables DROP rules (with counters)
cat data/blacklist/blacklist-outbound-ips.txt
```

### Cleanup False Positives

```bash
itsup monitor cleanup
```

Interactive: compares the blacklist against OpenSnitch blocks (primary) and DNS
history (fallback), then offers to move likely false positives to the whitelist and
rewrite the blacklist with the kept IPs.

### Generate Threat Report

```bash
itsup monitor report
```

Runs `bin/analyze_threats.py`, which analyzes each blacklisted IP (reverse DNS,
RDAP/whois, and AbuseIPDB if `ABUSEIPDB_API_KEY` is set in secrets) and writes
`reports/potential_threat_actors.csv`. Only IPs not already in the report are
re-analyzed.

### Unblock an IP

The supported path is to whitelist it (the monitor then removes both the blacklist
entry and the iptables rule automatically on reload):

```bash
echo "<dest_ip>   # reason" >> data/whitelist/whitelist-outbound-ips.txt
```

To clear **all** monitor iptables rules at once (LOG + every DROP) without touching
the list files:

```bash
itsup monitor clear-iptables
```

## Workload & Endpoint Health Checks (available, not yet wired in)

Two standalone health-check scripts ship in `bin/`. **Neither is currently invoked
by anything** — no systemd unit, no timer, no `itsup` subcommand, and not by
`bin/pi-healthcheck.sh` (which only checks host vitals). Wiring them into automation
is a pending operator decision; they are documented here so they are discoverable.

### `bin/workload-healthcheck.py` — container state/health

Iterates all enabled projects and, for each compose service, runs `docker ps`
(filtered by compose project/service labels) and `docker inspect`. A service fails if
it has no running container (`no_container`), is not in `running` state
(`state=<x>`), or — **only when the compose service declares a `healthcheck`** — its
Docker health is not `healthy` (`health=<x>`).

```bash
python3 bin/workload-healthcheck.py              # full FAIL/SUMMARY report
python3 bin/workload-healthcheck.py --quiet      # summary line only
python3 bin/workload-healthcheck.py --names-only # unique failing project names (one per line)
```

Exit codes: `0` healthy, `1` failures, `2` hard errors. `--names-only` is designed
to feed restart/remediation automation.

### `bin/check-endpoints.py` — external HTTPS reachability

Iterates all project ingress definitions and probes each HTTPS-eligible endpoint
from the outside (real `HTTPS` GET through TLS). The path is inferred from the
compose service's `healthcheck` URL when its port matches the ingress port,
otherwise from the ingress `path_prefix`, otherwise `/`. Status 200–399 is OK.

```bash
python3 bin/check-endpoints.py               # OK/FAIL/SKIP lines + SUMMARY
python3 bin/check-endpoints.py --timeout 5   # per-request timeout (default 10s)
```

Exit code `1` if any endpoint fails, else `0`.

## Security Database Policy

### Critical Rules

🚨 **NEVER MODIFY OR MOVE THE OPENSNITCH DATABASE** 🚨

- **Location**: `/var/lib/opensnitch/opensnitch.sqlite3`
- **Access**: READ-ONLY (SELECT queries only)
- **Purpose**: permanent security audit log

**Forbidden Operations**:
- ❌ DELETE / UPDATE queries
- ❌ `mv`, `cp`, `rm` on the database file
- ❌ moving, renaming, or altering the schema

**Why**: historical block data is critical for forensics, threat analysis, and
incident investigation.

**Handling False Positives**: modify the whitelist/blacklist files and let the
monitor update iptables. Never delete database entries.

## Troubleshooting

### OpenSnitch loopback wedge (deploys / cert renewals silently break)

OpenSnitch intercepts new TCP SYNs via NFQUEUE — **including loopback**. If
`opensnitchd` stalls, new loopback TCP connections wedge. That breaks
Traefik → docker-socket-proxy over the loopback interface, so new deploys and
TLS certificate renewals fail silently with no obvious error.

**Symptom**: deploys and cert renewals stop working, nothing obviously logged.

**Fix**:
```bash
sudo systemctl restart opensnitch
```

(Full root-cause write-up lives in the networking troubleshooting docs.)

### Monitor won't start

```bash
# Must run as root (iptables + journalctl -k require it)
sudo python3 bin/monitor.py

# --use-opensnitch requires the DB to exist; otherwise drop the flag
ls -lh /var/lib/opensnitch/opensnitch.sqlite3
```

### High false-positive rate

Run in report-only mode, review which IPs are being flagged, then whitelist the
verified dedicated-infra IPs (keeping cloud-provider ranges blacklisted — see
[False Positives](#false-positives)):

```bash
itsup monitor stop
itsup monitor start --report-only
grep "HARDCODED IP" logs/monitor.log | sort | uniq -c
echo "<verified_ip>   # reason" >> data/whitelist/whitelist-outbound-ips.txt
```

### Blocked legitimate traffic

```bash
# Whitelist it — the monitor auto-removes it from blacklist + iptables on reload
echo "<dest_ip>   # reason" >> data/whitelist/whitelist-outbound-ips.txt
```

## Best Practices

- **Start in report-only mode** for the first 1–2 weeks; review logs daily and tune
  the whitelist before enabling blocking.
- **Watch blacklist growth** — sustained growth signals tuning is needed.
- **Whitelist only verified dedicated-infra IPs**; never blanket-whitelist
  cloud-provider ranges.
- **Periodically** run `itsup monitor cleanup` (against OpenSnitch) and
  `itsup monitor report` for a forensic snapshot.
