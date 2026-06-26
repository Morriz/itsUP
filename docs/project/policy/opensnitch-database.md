---
description: 'The OpenSnitch SQLite database is a read-only forensic audit log: the monitor issues SELECT queries only and never modifies, deletes, moves, or copies the DB file. False positives are handled via whitelist/blacklist and iptables, never by editing the DB.'
---

# OpenSnitch Database — Policy

## Rules

- The OpenSnitch database at `/var/lib/opensnitch/opensnitch.sqlite3` is
  **read-only**. Only `SELECT` queries are permitted against it.
- **Never** issue `DELETE`, `UPDATE`, `INSERT`, or any schema-altering statement.
- **Never** `mv`, `cp`, `rm`, rename, truncate, or otherwise touch the database
  file or its journal/WAL siblings.
- Handle false positives by editing the monitor's own files —
  `data/whitelist/whitelist-outbound-ips.txt` and
  `data/blacklist/blacklist-outbound-ips.txt` — and the iptables rules. Never by
  removing rows from the OpenSnitch DB.
- The DB path is resolved from `OPENSNITCH_DB` (env override, default
  `/var/lib/opensnitch/opensnitch.sqlite3`); this policy applies to whatever path
  that resolves to (`monitor/constants.py:18`).

## Rationale

The OpenSnitch DB is the durable forensic record of blocked connections. Its
historical `0-deny-arpa-53` (reverse-DNS) blocks are the ground truth the monitor
cross-references to confirm threats and to validate the blacklist during cleanup
(`monitor/opensnitch.py`, `bin/monitor.py:cleanup_blacklist`). Mutating or moving
the file destroys evidence used for incident investigation and breaks the
monitor's confirmation path. The monitor enforces this in code: every access is a
`sqlite3` connection that runs `SELECT`-only queries
(`monitor/opensnitch.py:get_recent_block_count`, `get_all_arpa_blocks`,
`monitor_blocks`; `bin/monitor.py:cleanup_blacklist`).

## Scope

- The OpenSnitch SQLite database file at `/var/lib/opensnitch/opensnitch.sqlite3`
  (or the `OPENSNITCH_DB` override).
- All agents and operators interacting with that file, whether through the monitor
  code, the `--use-opensnitch` integration, or an ad-hoc `sqlite3` session.

## Enforcement

- Monitor code accesses the DB exclusively through
  `monitor/opensnitch.py:OpenSnitchIntegration` and the cleanup reader in
  `bin/monitor.py`, both of which issue `SELECT`-only statements. New code that
  needs OpenSnitch data routes through these read paths.
- Any write, move, or delete operation against the DB file is a policy violation.
- This snippet is the canonical home for the rule; it is surfaced always-on by
  inflation into the generated `AGENTS.md` via `docs/project/baseline.md`.

## Exceptions

None.

## See Also

- docs/project/design/container-security-monitor.md
- docs/project/design/security-architecture.md
