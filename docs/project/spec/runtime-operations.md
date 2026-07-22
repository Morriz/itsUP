---
description: 'Canonical truth for itsUP scheduled/triggered runtime operations — bringup, nightly apply, nightly backup, the 5-minute pi-healthcheck, and the container security monitor — with each one''s real trigger, frequency, responsibility, user-visible failure symptom, self-recovery, first operator checks, and safe recovery action for fast failure diagnosis.'
---

# Runtime Operations — Spec

## What it is

<!-- planned-change:native-daemon-supervision -->
itsUP runs a small set of unattended runtime operations on the **container host**
(the machine whose IP equals `SSH_HOST`): one boot-time bringup, two nightly
timers (apply, backup), a 5-minute health watchdog, and a long-running container
security monitor. Each is installed by `bin/install-bringup.sh` — run via
`make install-runtime`, separately from the dependency-only `make install` — as a
systemd unit/timer (Linux) or launchd job (macOS).
<!-- change:native-daemon-supervision -->
itsUP runs a small set of unattended runtime operations on the **container host**
(the machine whose IP equals `SSH_HOST`): one boot-time bringup, two nightly
timers (apply, backup), a 5-minute health watchdog, and two long-running daemons
— the API server and the container security monitor. Each is installed by
`bin/install-bringup.sh` — run via `make install-runtime`, separately from the
dependency-only `make install` — as a systemd unit/timer (Linux) or launchd job
(macOS). The monitor is Linux-only.
<!-- /planned-change:native-daemon-supervision -->

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
<!-- planned-change:native-daemon-supervision -->
| **bringup** | event (boot) | Once per boot; stays resident | `itsup run && itsup apply`: start DNS→proxy→API→monitor (report-only), then regen + deploy all stacks/projects. On shutdown runs `itsup down` (containers left `exited`, not removed, for sub-second restart). | After a reboot nothing is reachable — no DNS, no Traefik, sites down. | partial (Docker restart policy revives `exited` containers on next boot, but a failed `run`/`apply` is not retried) | `systemctl status itsup-bringup.service` then `journalctl -u itsup-bringup.service` (Linux); `~/Library/Logs/itsup.bringup.log` (macOS). Confirm `proxynet` exists: `docker network ls \| grep proxynet`. | Re-run manually from repo root on the host: `.venv/bin/itsup run && .venv/bin/itsup apply`. |
<!-- change:native-daemon-supervision -->
| **bringup** | event (boot) | Once per boot; stays resident | `itsup run && itsup apply`: start DNS→proxy, then start the API and monitor units through the host supervisor (monitor in report-only), then regen + deploy all stacks/projects. On shutdown runs `itsup down` (containers left `exited`, not removed, for sub-second restart; the two daemon units are stopped). | After a reboot nothing is reachable — no DNS, no Traefik, sites down. | partial (Docker restart policy revives `exited` containers on next boot, and each daemon unit restarts itself on crash; a failed `run`/`apply` is **not** retried by systemd on Linux, but on macOS launchd relaunches the guardian under `KeepAlive`, so it retries there) | `systemctl status itsup-bringup.service` then `journalctl -u itsup-bringup.service` (Linux); `~/Library/Logs/itsup.bringup.log` (macOS). Confirm `proxynet` exists: `docker network ls \| grep proxynet`. | Re-run manually from repo root on the host: `.venv/bin/itsup run && .venv/bin/itsup apply`. |
<!-- /planned-change:native-daemon-supervision -->
| **apply** (nightly) | timer | Nightly 03:00 local (`OnCalendar=*-*-* 03:00:00`, `Persistent=true` → catches up after downtime) | Validates the whole config (fail-closed), regenerates compose+Traefik labels, deploys all stacks + projects topo-ordered with smart rollout (pulls fresh images, hash-based skip if unchanged). | Config edits / image updates silently never go live; sites keep serving stale config. | partial (`Persistent=true` runs a missed timer once on next boot; a validation/deploy failure exits non-zero and is **not** retried until next night) | `systemctl status itsup-apply.service` + `journalctl -u itsup-apply.service`; run `itsup validate` to see the fail-closed gate's errors. | Fix validation errors, then `.venv/bin/itsup apply` (or `.venv/bin/itsup apply <project>` for one). |
| **backup** (nightly) | timer | Nightly 05:00 local (`OnCalendar=*-*-* 05:00:00`, `Persistent=true`) | tars `upstream/` (excludes each project's `backup.yml` `exclude` paths; skips files that vanish mid-walk), uploads timestamped object to S3, keeps newest 10. Runs as **root** with `HOME` pinned to the itsUP user so SOPS finds the age key. | No new dated object appears in the S3 bucket; oldest restore point ages out. | no (aborts on missing AWS_* secrets or upload error; next run is 24h later) | `journalctl -u itsup-backup.service` (look for `Missing required secrets` or S3 errors); confirm `secrets/itsup.enc.txt` decrypts and carries `AWS_ACCESS_KEY_ID/SECRET/S3_HOST/REGION/BUCKET`. | `.venv/bin/python bin/backup.py` (run with the same HOME so SOPS can decrypt). |
<!-- planned-change:fix-pi-healthcheck-writes-run-state-as-an-un -->
| **pi-healthcheck** | timer | Every 5 min (`OnBootSec=5min`, `OnUnitActiveSec=5min`) | Checks mem/load/conntrack/disk and `docker ps`. Outside 02:30–03:30 it is **log-only** except break-glass thresholds (3-strike → restart docker + `itsup dns up`/`proxy up`). Inside the window it restarts docker+stacks on 1st strike (stamp `/run/pi-healthcheck.fail`), **reboots host** on 2nd. | Either silent (healthy) or, on a real degradation, an automatic stack restart / host reboot the operator did not initiate. | yes (this *is* the auto-recovery: restart stacks, then reboot if that fails) | `journalctl -u pi-healthcheck.service`; check `/run/pi-healthcheck.fail` and `/run/pi-healthcheck.strikes` for active strikes. | If false-tripping, clear strike state: `rm -f /run/pi-healthcheck.strikes /run/pi-healthcheck.fail`. To stop auto-action while debugging: `systemctl stop pi-healthcheck.timer`. |
<!-- change:fix-pi-healthcheck-writes-run-state-as-an-un -->
| **pi-healthcheck** | timer | Every 5 min (`OnBootSec=5min`, `OnUnitActiveSec=5min`) | Checks mem/load/conntrack/disk and `docker ps`. Outside 02:30–03:30 it is **log-only** except break-glass thresholds (3-strike → restart docker + `itsup dns up`/`proxy up`). Inside the window it restarts docker+stacks on 1st strike (stamp `/run/itsup/pi-healthcheck.fail`), **reboots host** on 2nd. Strike state lives in the unit's own `RuntimeDirectory=itsup` (`/run/itsup`), created at unit start owned by its `User=` and held across runs by `RuntimeDirectoryPreserve=yes`; `/run` is tmpfs, so it clears on reboot. | Either silent (healthy) or, on a real degradation, an automatic stack restart / host reboot the operator did not initiate. | yes (this *is* the auto-recovery: restart stacks, then reboot if that fails) | `journalctl -u pi-healthcheck.service`; check `/run/itsup/pi-healthcheck.fail` and `/run/itsup/pi-healthcheck.strikes` for active strikes. | If false-tripping, clear strike state: `rm -f /run/itsup/pi-healthcheck.strikes /run/itsup/pi-healthcheck.fail`. To stop auto-action while debugging: `systemctl stop pi-healthcheck.timer`. |
<!-- /planned-change:fix-pi-healthcheck-writes-run-state-as-an-un -->

<!-- planned-change:native-daemon-supervision -->
| **container security monitor** | manual / event (started by bringup) | Continuous daemon (started by `itsup run` in **report-only** mode; `itsup monitor start` for blocking) | `bin/monitor.py`: watches container network activity, logs to `logs/monitor.log`; in blocking mode adds iptables DROP rules for blacklisted IPs (report-only = detect, no block). | None for traffic in report-only; in blocking mode a false positive can DROP legitimate egress for a container. | no (a killed process is not respawned outside the next bringup) | `tail -f logs/monitor.log`; `pgrep -f bin/monitor.py`; for a suspected false block run `itsup monitor cleanup` (OpenSnitch-verified blacklist false-positive review). | `itsup monitor start --report-only` to restart detection-only; `itsup monitor stop` then `itsup monitor clear-iptables` to remove the monitor's iptables rules. |
<!-- change:native-daemon-supervision -->
| **API server** | event (started by `itsup run`) | Continuous daemon (`itsup-api.service` on Linux, the `ai.itsup.api` launchd agent on macOS) | Serves the itsUP management API on `:8888` (`api/main.py` under uvicorn). Runs as the itsUP user, logs plainly to the supervisor's journal, and restarts itself on crash. Installation writes the supervisor definition and issues no per-daemon supervisor verb against it — on Linux it may invoke one ordered whole-stack `itsup run` directly while the host's supervision cutover is pending, and none directly once that has completed; on macOS it never runs directly at all, reloading the bringup agent instead so that agent's guardian performs the run; independently of that, an install restarts bringup whenever its definition changed or it was inactive, and that unit's `ExecStart=itsup run` starts the stack, so a changed definition stays inert until the API is next brought up in a way that re-reads it — on Linux `sudo systemctl restart itsup-api`, the API's own self-restart, or a crash respawn (systemd restarts against its reloaded unit); on macOS `itsup down` then `itsup run`, since neither `kickstart -k` nor a `KeepAlive` respawn re-registers the plist. `itsup run` alone does not apply it to a running API on either platform. The Linux unit carries no `[Install]` section and is never enabled, and the macOS agent's plist is written but not bootstrapped; an install can still start it indirectly, by restarting the bringup unit (systemd) or bootstrapping the bringup agent (launchd), either of which runs `itsup run` — the same ordered path, never a direct action on this daemon. | Webhook deploys and `/reconcile` stop answering; on Linux the unit shows `failed` or a restart loop. | yes (`Restart=always`, bounded by `StartLimitIntervalSec=300`/`StartLimitBurst=5` so a sustained crash loop reaches `failed` in ~30s while an isolated crash does not; launchd `KeepAlive` respawns after a crash on macOS) | `systemctl status itsup-api` and `journalctl -u itsup-api` (Linux); `~/Library/Logs/itsup.api.log` (macOS). A restart does not truncate the history — the prior lines are still there. | `sudo systemctl restart itsup-api` (Linux) / `launchctl kickstart -k gui/$(id -u)/ai.itsup.api` (macOS). |
| **container security monitor** | event (started by `itsup run`) | Continuous daemon (`itsup-monitor.service`, started by `itsup run` in **report-only** mode; `itsup monitor start` for blocking). The unit carries no `[Install]` section and is never enabled, so it is activated only by `itsup run` as part of the ordered stack, or by `itsup monitor start` as an explicit single-unit operator transition. Installation issues no per-daemon supervisor verb against it, so a changed unit definition stays inert until something restarts the unit — `itsup monitor start`, `sudo systemctl restart itsup-monitor`, a crash respawn, or any `itsup run`, whose monitor step rewrites `MONITOR_FLAGS` and restarts it (which also returns the mode to report-only). This differs from the API, whose `run` step is a start verb and applies nothing to a running process. Linux only. | `bin/monitor.py`: watches container network activity and in blocking mode adds iptables DROP rules for blacklisted IPs (report-only = detect, no block). Runs as root with `HOME` pinned to the itsUP user; diagnostics go to the journal. Its mode comes from `MONITOR_FLAGS` in the host-local `.itsup-monitor.env`, which `itsup monitor start` and `itsup run` write; with the file absent it starts in blocking mode. `logs/monitor.log` remains the restart watermark, not a log. | None for traffic in report-only; in blocking mode a false positive can DROP legitimate egress for a container. | yes (`Restart=always`, bounded by `StartLimitIntervalSec=300`/`StartLimitBurst=5` so a sustained crash loop reaches `failed` rather than restarting forever) | `systemctl status itsup-monitor` and `journalctl -u itsup-monitor`; confirm the active mode with `cat .itsup-monitor.env`; for a suspected false block run `itsup monitor cleanup` (OpenSnitch-verified blacklist false-positive review). | `itsup monitor start --report-only` to switch to detection-only; `itsup monitor stop` then `itsup monitor clear-iptables` to remove the monitor's iptables rules. |
<!-- /planned-change:native-daemon-supervision -->

<!-- planned:ops-failure-alerting -->
| **failure alert** | event (a covered unit enters the `failed` state) | Once per unit failure for units without `Restart=`; for the always-restarting API and monitor daemons, once per start-limit exhaustion rather than per crash | Templated systemd unit run by every covered unit's `OnFailure=` hook. Composes a subject plus the failed unit's recent journal lines and pipes the result to the command in `alert.command` (`project/spec/itsup-config`). With the key unset it runs no command, records the suppressed alert in the journal, and exits 0. Runs as the itsUP user, never as root: journal reads come from `systemd-journal` group membership ensured at install, and SOPS decrypts the infra secrets the template's `${VAR}` placeholders resolve from using that user's own key. Operator-configured transport code executes without elevated privilege. The alert unit carries no `OnFailure=` of its own. A failing alert does not alert about itself. Linux/systemd only — launchd has no `OnFailure` equivalent, so macOS hosts have no failure hook. | The operator's configured channel stays silent while units fail. | no (a failed alert attempt is not retried; the composer's own failure is in its journal) | `journalctl -u 'itsup-alert@*'` for composer runs and their outcome; confirm the key with `grep -A2 '^alert:' projects/itsup.yml`; confirm the referenced secret is present in `secrets/itsup.enc.txt`. | Compose against a unit by hand on the host, as the itsUP user: `.venv/bin/python bin/alert.py <unit>`. |
| **apply deadman** | timer (asserted by pi-healthcheck) | Every 5 min, alongside the host vitals | Asserts the age of the last successful nightly apply — a stamp the apply and bringup units write only on success — and composes an alert through the same command when it exceeds the expected window. Catches the failure class the `OnFailure=` hook cannot see: a masked unit, or a timer that never fired. Re-alerting is suppressed while the same stale period persists, so one stale apply yields one alert, not one per assertion. | Config edits and image updates silently never go live and nothing reports it. | no (the assertion repeats every 5 min; recovery is a successful apply, which refreshes the stamp) | `journalctl -u pi-healthcheck.service` for the assertion's verdict; check the stamp's age against the window. | Run `.venv/bin/itsup apply` on the host — a successful apply refreshes the stamp and clears the assertion. |
<!-- /planned:ops-failure-alerting -->

## Known caveats

<!-- planned:native-daemon-supervision -->

- **The supervision cutover record is host state, and its absence is not a
  licence to restart the stack.** `.itsup-supervision-state` at the install root
  holds exactly one of the literals `attempting` or `complete`, written
  atomically. Any other content — empty, malformed, truncated — is **unreadable**
  rather than absent, and the install fails closed on it: absence means never
  attempted, an unreadable value means unknown, and guessing between them would
  restart a stack the operator had deliberately stopped. Recovery writes the
  intended state explicitly **and atomically**, by the same temp-file-and-rename
  route every other writer uses:
  `printf 'complete\n' > .itsup-supervision-state.tmp && mv
  .itsup-supervision-state.tmp .itsup-supervision-state`. A plain redirection
  truncates before it writes, so an interrupted recovery would leave the empty
  state the contract calls unreadable; `touch` produces that state outright. The installer writes
  `attempting` before it writes any daemon definition; the record advances to `complete` only when a
  path that observed an ordered `itsup run` exit zero records it. No path
  records a run it did not observe. `make uninstall-runtime` removes the record.

  `make install-runtime` classifies the host from that record plus whether the
  daemon definitions already existed and were registered: no record and no
  pre-existing registered definitions is a fresh cutover, which it performs;
  `attempting` is an unfinished attempt, which it retries; `complete` is done.
  No record **with** definitions already registered is ambiguous — the record was
  lost after a cutover — and the install **fails closed**: it starts nothing,
  exits non-zero, and prints the recovery choice (run `itsup run` manually, or
  write `complete` if the host is already as intended). An absent record never
  causes an automatic whole-stack start on an initialised host, because that
  would revive a deliberately stopped daemon.

  **Run ownership and retry differ by supervisor.** On Linux the bringup unit is
  `Type=oneshot` with no `Restart=`, so a failed run is not retried by systemd;
  `systemctl restart` returns its result, and the installer owns both the
  outcome and the retry on the next invocation. On macOS the guardian runs under
  `set -euo pipefail` and its agent declares `KeepAlive={SuccessfulExit: false}`,
  so a failed run exits the guardian and launchd relaunches it — the guardian
  owns the retry. The installer performs no direct run there.
  While the cutover is fresh or `attempting` it reloads the bringup agent even
  when its plist is unchanged — the only launchd-owned way to make a resident
  guardian execute a new run — then waits for the record to reach `complete`,
  polling every 2 s for up to 300 s, and exits non-zero on timeout.

<!-- /planned:native-daemon-supervision -->


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
