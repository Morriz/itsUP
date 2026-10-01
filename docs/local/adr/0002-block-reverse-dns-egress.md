---
description: 'itsUP installs the 0-deny-arpa-53 OpenSnitch rule to deny reverse-DNS lookups on direct-IP egress, dropping hardcoded-IP C2 connections while leaving DNS-resolved traffic intact, because L7/CrowdSec defenses could not stop real-time key exfiltration.'
date: '2025-10-24'
number: 2
---

# Block Reverse-DNS Egress to Stop Hardcoded-IP Exfiltration — ADR

## Context

A container on the itsUP host was exfiltrating OpenAI API keys to an attacker in
real time: usage spiked ~300% and key rotation only restored normal usage for
minutes before unauthorized calls resumed. The exfiltration was contained at the
network layer, but the originating container and the implant were never
identified (`docs/security.md`).

The existing controls did not stop it:

- **Layer 7 / CrowdSec** banned HTTP probing (~50 IPs/day for
  `crowdsecurity/http-probing`) but had zero effect on the leak — the exfiltration
  was not HTTP, it was direct TCP.
- **DNS honeypot** monitoring of forward queries showed no suspicious domains over
  72 hours — only npm, GitHub, Microsoft Graph. The malware was connecting to
  **hardcoded C2 IP addresses**, deliberately skipping DNS to evade the honeypot.

Direct-IP egress was therefore the unguarded path, and it had to be closed
without breaking the legitimate outbound traffic of 20+ services that resolve
their endpoints via DNS.

## Decision

Install the OpenSnitch rule **`0-deny-arpa-53`** (`opensnitch/0-deny-arpa-53.json`)
and run a correlation engine (`bin/monitor.py`, `monitor/core.py`,
`monitor/opensnitch.py`) on top of its output.

The rule denies, with `precedence: true`, any connection where:

- `process.path` = `/usr/bin/dockerd`,
- `dest.port` = `53`, and
- `dest.host` matches the regexp `^(\d{1,3}\.){4}in-addr\.arpa$`.

The mechanism is OpenSnitch's designed behavior, not a side effect. When a
container connects to a **hardcoded IP** (no prior forward DNS), dockerd performs
a **reverse-DNS lookup** on that IP (`X.X.X.X.in-addr.arpa`). The rule matches
that reverse lookup and denies it; the direct-IP connection, which depends on the
lookup completing, fails. **Legitimate services resolve their endpoints by name
first**, match OpenSnitch by forward domain, and are unaffected — so the rule
drops direct-IP egress while leaving DNS-resolved traffic intact.

On top of the rule, the correlation engine reads denied rows
(`rule = '0-deny-arpa-53'`, `dst_host LIKE '%.in-addr.arpa'`) from OpenSnitch's
SQLite store, extracts the IP (`extract_ip_from_arpa`), and for any IP with no
forward-DNS history in the honeypot cache adds an iptables DROP and flags the
connecting container as compromised.

## Consequences

- **Positive — exfiltration contained.** Validated reproducibly: disabling the
  rule resumed exfiltration within minutes, re-enabling it stopped it. Zero key
  exfiltrations and zero unauthorized OpenAI calls since the block
  (`docs/security.md`).
- **Positive — no collateral damage.** No legitimate service was broken; DNS-using
  traffic is unaffected by design. ~5–10 new malicious IPs auto-blacklisted per
  day, with high AbuseIPDB confidence.
- **Negative — depends on OpenSnitch's reverse-DNS-on-connect behavior.** The
  fail-closed property rests on dockerd/OpenSnitch performing a reverse-DNS lookup
  for direct-IP connections. If OpenSnitch is absent or a future version changes
  that behavior, the guarantee is lost; the monitor then falls back to
  iptables/journalctl + honeypot correlation, which needs more validation.
- **Negative — does not stop DNS-resolving malware.** Only *direct-IP* egress is
  blocked. Malware that resolves an attacker domain first gains DNS history and is
  treated as legitimate; this layer is one of several (see
  `docs/project/design/security-architecture.md`), not a complete egress control.
- **Negative — implant not removed.** The compromised container remains
  unidentified; this decision contains the symptom (exfiltration) rather than
  removing the cause. The attacker is assumed still present.
- **Operational — OpenSnitch is the source of truth.** The monitor's high-confidence
  path requires the OpenSnitch DB; the rule and engine compose
  (`docs/project/design/container-security-monitor.md`).

## Alternatives Considered

- **Rely on L7/CrowdSec only.** Rejected — empirically ineffective against direct
  TCP exfiltration; it bans HTTP probers, not C2 connections.
- **Block on forward-DNS domains via the honeypot.** Rejected as the primary
  control — the malware used hardcoded IPs and never appeared in forward-DNS logs,
  so there was no domain to block.
- **Audit and patch the compromised container first.** Rejected as the immediate
  response — auditing 20+ containers for supply-chain/backdoor/zero-day implants is
  slow, and the leak was active; the egress block stops the bleeding while the
  audit proceeds in the background.

## Status

Accepted and active.
