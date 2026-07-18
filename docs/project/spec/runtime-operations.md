---
description: 'Canonical truth for itsUP scheduled/triggered runtime operations — bringup, nightly apply, nightly backup, the 5-minute pi-healthcheck, and the container security monitor — with each one''s real trigger, frequency, responsibility, user-visible failure symptom, self-recovery, first operator checks, and safe recovery action for fast failure diagnosis.'
---

# Runtime Operations — Spec

## What it is

itsUP runs a small set of unattended runtime operations on the **container host**
(the machine whose IP equals `SSH_HOST`): one boot-time bringup, two nightly
timers (apply, backup), a 5-minute health watchdog, and a long-running container
security monitor. Each is installed by `bin/install-bringup.sh` — run via
`make install-runtime`, separately from the dependency-only `make install` — as a
systemd unit/timer (Linux) or launchd job (macOS).

This spec is the single place an operator goes when one of those operations
fails: for each operation it records what fires it, how often, what it actually
does, the symptom a user sees when it breaks, whether it recovers itself, the
first checks to run, and the safe action to recover. It deliberately covers
**only itsUP-specific operations** — generic Docker/Traefik/systemd
troubleshooting is out of scope and belongs to the platform debugging procedure
and the upstream tools' own docs.

## Canonical fields

### Operator intervention

- Normal desired-state delivery is GitOps reconciliation. A manual apply is not a routine
  continuation of a successful commit.
- A failed reconciliation opens an operational investigation: establish the failure from
  pipeline or host evidence, inspect read-only state first, then address the verified cause.
- `itsup apply <project>` is an available targeted recovery when automated reconciliation did
  not bring the committed desired state live. It is not used pre-emptively.
- Runtime mutation stays proportional: one project before the fleet, one service before a
  stack, and no restart merely because a health status is red. Determine whether the service,
  its dependency, or its healthcheck is actually defective.
- Broad-blast-radius actions against shared proxy, DNS, database, Docker daemon, or the host
  are not exploratory troubleshooting. After the cause is evidenced, they require explicit
  human ratification unless an already-defined automatic recovery operation owns the action.
- When manual mutation is required beyond normal GitOps reconciliation, record the failure,
  intervention, and outcome. File a bug when the evidence exposes a platform defect or missing
  recovery behavior.

The triggers and frequencies below are read from the installed units/timers and
the scripts they invoke; if a unit is edited, this table drifts (see Known
caveats).

| Operation | Trigger | Run frequency | What it does | User-visible failure symptom | Self-recovery | First checks | Safe recovery action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **bringup** | event (boot) | Once per boot; stays resident | `itsup run && itsup apply`: start DNS→proxy→API→monitor (report-only), then regen + deploy all stacks/projects. On shutdown runs `itsup down` (containers left `exited`, not removed, for sub-second restart). | After a reboot nothing is reachable — no DNS, no Traefik, sites down. | partial (Docker restart policy revives `exited` containers on next boot, but a failed `run`/`apply` is not retried) | `systemctl status itsup-bringup.service` then `journalctl -u itsup-bringup.service` (Linux); `/var/log/instrukt-ai/itsup/bringup.log` (macOS). Confirm `proxynet` exists: `docker network ls \| grep proxynet`. | Re-run manually from repo root on the host: `.venv/bin/itsup run && .venv/bin/itsup apply`. |
| **apply** (nightly) | timer | Nightly 03:00 local (`OnCalendar=*-*-* 03:00:00`, `Persistent=true` → catches up after downtime) | Validates the whole config (fail-closed), regenerates compose+Traefik labels, deploys all stacks + projects topo-ordered with smart rollout (pulls fresh images, hash-based skip if unchanged). | Config edits / image updates silently never go live; sites keep serving stale config. | partial (`Persistent=true` runs a missed timer once on next boot; a validation/deploy failure exits non-zero and is **not** retried until next night) | `systemctl status itsup-apply.service` + `journalctl -u itsup-apply.service`; run `itsup validate` to see the fail-closed gate's errors. | Fix validation errors, then `.venv/bin/itsup apply` (or `.venv/bin/itsup apply <project>` for one). |
| **backup** (nightly) | timer | Nightly 05:00 local (`OnCalendar=*-*-* 05:00:00`, `Persistent=true`) | tars `upstream/` (excludes each project's `backup.yml` `exclude` paths; skips files that vanish mid-walk), uploads timestamped object to S3, keeps newest 10. Runs as **root** with `HOME` pinned to the itsUP user so SOPS finds the age key. | No new dated object appears in the S3 bucket; oldest restore point ages out. | no (aborts on missing AWS_* secrets or upload error; next run is 24h later) | `journalctl -u itsup-backup.service` (look for `Missing required secrets` or S3 errors); confirm `secrets/itsup.enc.txt` decrypts and carries `AWS_ACCESS_KEY_ID/SECRET/S3_HOST/REGION/BUCKET`. | `.venv/bin/python bin/backup.py` (run with the same HOME so SOPS can decrypt). |
| **pi-healthcheck** | timer | Every 5 min (`OnBootSec=5min`, `OnUnitActiveSec=5min`) | Checks mem/load/conntrack/disk and `docker ps`. Outside 02:30–03:30 it is **log-only** except break-glass thresholds (3-strike → restart docker + `itsup dns up`/`proxy up`). Inside the window it restarts docker+stacks on 1st strike (stamp `/run/pi-healthcheck.fail`), **reboots host** on 2nd. | Either silent (healthy) or, on a real degradation, an automatic stack restart / host reboot the operator did not initiate. | yes (this *is* the auto-recovery: restart stacks, then reboot if that fails) | `journalctl -u pi-healthcheck.service`; check `/run/pi-healthcheck.fail` and `/run/pi-healthcheck.strikes` for active strikes. | If false-tripping, clear strike state: `rm -f /run/pi-healthcheck.strikes /run/pi-healthcheck.fail`. To stop auto-action while debugging: `systemctl stop pi-healthcheck.timer`. |
| **container security monitor** | manual / event (started by bringup) | Continuous daemon (started by `itsup run` in **report-only** mode; `itsup monitor start` for blocking) | `bin/monitor.py`: watches container network activity, logs to `logs/monitor.log`; in blocking mode adds iptables DROP rules for blacklisted IPs (report-only = detect, no block). | None for traffic in report-only; in blocking mode a false positive can DROP legitimate egress for a container. | no (a killed process is not respawned outside the next bringup) | `tail -f logs/monitor.log`; `pgrep -f bin/monitor.py`; for a suspected false block run `itsup monitor cleanup` (OpenSnitch-verified blacklist false-positive review). | `itsup monitor start --report-only` to restart detection-only; `itsup monitor stop` then `itsup monitor clear-iptables` to remove the monitor's iptables rules. |

## Known caveats

- **Frequencies drift if units change.** The 03:00/05:00/5-min schedules and the
  bringup `run && apply` command are read from `samples/systemd/*.timer` /
  `*.service` and `samples/launchd/ai.itsup.*.plist`. Editing a unit (or the
  scripts it calls — `bin/pi-healthcheck.sh`, `bin/backup.py`,
  `bin/bringup-guardian.sh`) without updating this table makes the table stale;
  the installed unit is the truth, not this doc.
- **`proxynet` is created by the DNS stack, not the proxy.** The `proxynet`
  network (`172.20.0.0/16`, gateway/honeypot `172.20.0.1`/`172.20.0.253`
  reserved) is created in `dns/docker-compose.yml`, which is why bringup/apply
  start DNS first. If proxy or a project fails with a missing/external network
  error, **first check `docker network ls | grep proxynet`** and bring DNS up
  (`itsup dns up`) before anything else.
- **Backup secret-loading is HOME-sensitive.** The backup unit runs as root but
  pins `HOME` to the itsUP user so SOPS finds `~/.config/sops/age/keys.txt`.
  Running `bin/backup.py` as root with the default `/root` HOME makes
  `load_secrets()` return empty and the run aborts with
  `Missing required secrets` — the first check on a backup failure is the SOPS
  key path, not the AWS credentials themselves.
- **Per-context secrets, not merged.** Infra operations (run/apply of dns/proxy,
  backup) load `secrets/itsup.{enc.txt|txt}`; a project deploy loads only
  `secrets/<project>.{enc.txt|txt}` and does **not** inherit itsUP secrets.
  Always launch compose via `get_env_with_secrets(<project>)` (or
  `get_env_with_secrets()` for infra) — a missing project secrets file surfaces
  as unexpanded `${VAR}` at deploy, not as an error.
- **`itsup apply` runs only on the container host.** It has no remote target and
  deploys from inside the repo on the host whose IP equals `SSH_HOST`. The
  nightly timer and bringup both assume this; running apply on any other machine
  spins the whole stack up locally.
- **`make install-runtime` is idempotent by content — a no-op re-run causes no
  stack downtime.** `bin/install-bringup.sh` only writes a rendered unit/plist
  when its content differs from what's already on disk, and only restarts
  `itsup-bringup.service` (or reloads the `ai.itsup.bringup` launchd agent) when
  that unit/plist actually changed or the service/agent isn't currently active.
  Because `itsup-bringup.service` is `Type=oneshot` with `RemainAfterExit=yes`
  and `ExecStop=itsup down`, an unconditional restart would otherwise stop every
  upstream project before starting them back up on every install invocation,
  regardless of whether anything changed.

## See Also

- docs/project/spec/cli.md — non-obvious run/down/apply CLI semantics.
- docs/project/spec/secrets-management.md — SOPS/age loading and ${VAR} passthrough.
- docs/project/design/network-segmentation.md — proxynet/ingress/egress design.
