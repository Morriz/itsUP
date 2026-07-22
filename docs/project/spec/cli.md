---
description: 'Non-obvious itsup CLI semantics not visible in --help — the run/down orchestration order, apply''s fail-closed validate gate plus sequential topo-ordered deploy with label-based hash skip, and the only codified exit-code semantics (0/1 plus passed-through subprocess returncodes).'
---

# CLI — Spec

## What it is

`itsup` is the itsUP management CLI (`itsup.cli:main`, a Click group registering
the commands in `commands/`). This spec records only the behaviors that
`itsup --help` and the per-command `--help` do **not** reveal; distribution and
invocation are in `project/design/itsup-cli`, and per-context secret loading is
in `project/spec/secrets-management`.

## Canonical fields

### `run` / `down` orchestration order

<!-- planned-change:native-daemon-supervision -->
- `itsup run` starts the stack in dependency order: **DNS → proxy → API →
  monitor**, with the monitor in **report-only mode** (`start-monitor.sh
  --report-only`). Full blocking protection requires a separate `itsup monitor
  start`. Before starting anything, `run` regenerates proxy artifacts
  (`write_proxy_artifacts()`) and aborts if that fails. At boot it intentionally
  does **not** pull images (the host's own DNS may not be up yet). On any stack
  failure `run` exits with that stack's subprocess returncode.
  (`commands/run.py`)
- `itsup down` stops in the **reverse** order: **monitor → API → all upstream
  projects → proxy → DNS**. Upstream projects are stopped **in parallel**
  (`ThreadPoolExecutor`, max 10); the infra stacks are stopped sequentially.
  Monitor/API stops use `pkill` and proxy/DNS `down` failures are logged but
  **not fatal** — `down` completes regardless. `--clean` additionally `rm -f`s
  the stopped itsUP containers (projects + proxy + dns) in parallel and never
  touches non-itsUP containers. (`commands/down.py`)
<!-- change:native-daemon-supervision -->
- `itsup run` starts the stack in dependency order: **DNS → proxy → API →
  monitor**. The two container stacks come up through `docker compose`; the API
  and the monitor are **daemon units the host supervisor owns**, so `run` starts
  them through it rather than spawning processes of its own. The monitor starts
  in **report-only mode** — `run` writes that mode into the supervisor-read flags
  file before starting the unit — and full blocking protection requires a
  separate `itsup monitor start`. Before starting anything, `run` regenerates
  proxy artifacts (`write_proxy_artifacts()`) and aborts if that fails. At boot
  it intentionally does **not** pull images (the host's own DNS may not be up
  yet). On any stack failure `run` exits with that stack's subprocess
  returncode. On a host with no monitor support (macOS — the monitor is
  Linux-only) `run` skips the monitor step with a notice and continues.
  (`commands/run.py`)
- **`itsup run` is the sole starter of both daemons, on every platform.**
  Installation writes the supervisor definitions but never activates them: on
  Linux the units carry no `[Install]` section and are never enabled; on macOS
  the API agent's plist is written but not bootstrapped. Activation happens only
  at `run`'s own API and monitor steps — on macOS `run` bootstraps the agent,
  which is what starts it, since a `KeepAlive` job implies `RunAtLoad`. Once
  started, the supervisor owns crash recovery on both platforms. The order above
  therefore holds identically everywhere, and nothing activates a daemon behind
  the orchestrator's back.
- `itsup down` stops in the **reverse** order: **monitor → API → all upstream
  projects → proxy → DNS**. Upstream projects are stopped **in parallel**
  (`ThreadPoolExecutor`, max 10); the infra stacks are stopped sequentially. The
  monitor and API are stopped through the supervisor, and a unit that is already
  inactive is not an error; proxy/DNS `down` failures are logged but **not
  fatal** — `down` completes regardless. `--clean` additionally `rm -f`s the
  stopped itsUP containers (projects + proxy + dns) in parallel and never
  touches non-itsUP containers. (`commands/down.py`)
<!-- /planned-change:native-daemon-supervision -->

### `apply` — validate gate, sequential topo deploy, label-based hash skip

- `apply` first runs a **global, fail-closed** `validate_all()` design-by-contract
  gate: a single invalid project or cross-project collision blocks **every**
  deploy (exit 1) — even `itsup apply <one-project>` is refused while any project
  is invalid. (`commands/apply.py:45`)
- `itsup apply` (no argument) deploys **sequentially in topological order**
  (`list_projects_topo()`), prefixed by `dns` then `proxy` — it is **not**
  parallel. It collects failures and exits 1 if any target failed, after
  attempting all of them. (`commands/apply.py:90`)
- Change detection compares the **live** `docker compose config --hash <service>`
  against the running container's `com.docker.compose.config-hash` label — there
  is **no stored hash file**. Per stateless service, rollout is skipped when the
  hash matches, when the service was not running before (first-time deploy gets a
  plain `up -d`, no rollout), or when it is not the `--service` filter target. A
  failed individual rollout is logged and does not fail the deployment.
  (`lib/deploy.py:62`, `lib/deploy.py:257`)

<!-- planned:itsup-logs-router -->

### `logs` — the routing front door over fragmented log backends

`itsup logs [TARGET]` is the single entry point to itsUP's host-side logs. Each
target names a producer, and the command routes it to whichever backend actually
holds that producer's records; the operator never needs to know which. It is
host-only (see the gate below) and read-only.

**Bare invocation is discovery**: `itsup logs` with no target prints every
routable target with its description, one pair per line, and exits 0. An
unrecognised target exits 1 and prints the routable set. Every rejection the
router owns — unknown target, malformed option value, unavailable backend — exits
1; the CLI declares no exit-2 contract, so parameter failures are translated
rather than left to the parser's own usage exit.

**Targets and their backends.** Six supervised-unit targets — `api`, `monitor`,
`bringup`, `apply`, `backup`, `healthcheck` — plus the file-backed `access`
(Traefik's JSON access log under `logs/`, rendered through `bin/format-logs.py`).
The unit targets resolve per platform, following the supervision contract in
`project/design/logging`: on Linux to `journalctl -u <unit>`; on macOS to the
launchd agent's `StandardOutPath`, read from the installed agent's own plist so
the path comes from what launchd actually loaded. `monitor` and `healthcheck` are
Linux-only daemons and have no macOS agent, so on macOS they are refused with
that reason rather than routed to a file that will never exist.

There is deliberately **no `<project>` target** — container logs stay docker-led
through `itsup svc` / `proxy` / `dns` — and **no `cli` target**: interactive runs
are observed live, and their diagnostic file is read with `instrukt-ai-logs
itsup`.

**One option surface, translated per backend.** `-f/--follow`, `--since`, and
`--grep` mean the same thing on every target, and both filters apply to the
**operator-visible line** — the text the command prints — so a pattern matches
what the operator reads rather than an underlying representation they never see.

- `--since` takes the duration grammar `<n>{s,m,h,d}`. The journal's own
  `--since` rejects a bare duration, so the router parses the duration and hands
  the journal an absolute timestamp; a file backend compares the same cutoff
  against the time its own rendered line carries.
- `--grep` is a case-sensitive regular expression on every backend. The journal's
  default is smart-case, so the router pins `--case-sensitive=true` rather than
  letting the pattern's own casing change the contract.
- An invalid duration or an invalid regex is rejected at the option boundary with
  exit 1 before any backend is reached.

**`--since` has one designed exception: macOS unit targets.** Filtering by time
requires a per-line time, and the supervisor is what supplies it — journald does,
launchd does not. A launchd agent's `StandardOutPath` captures the daemon's
stream verbatim, and that stream deliberately carries no timestamp because the
supervisor is expected to add one. So `--since` against a macOS unit target exits
1 naming that reason, while `--follow` and `--grep` remain available there. The
`access` target is unaffected on either platform: its rendered line leads with
Traefik's own time.

**Every unavailability path refuses, never degrades.** A unit target with no
reader on this platform, and a unit target whose unit is not installed, each exit
1 naming the reason. Unit existence is established before the query — a unit is
usable only when its `LoadState` is `loaded`, and any other value is reported
rather than interpreted — because a journal query against an absent unit succeeds
with empty output.

<!-- /planned:itsup-logs-router -->

### Host-identity gate (runtime-mutating commands are host-only)

The CLI group refuses runtime-mutating commands on any machine that is not the
container host, before the command does any work. The host is the machine whose
own LAN IP equals `SSH_HOST` in `.env` — read from the file via `load_env_file`,
**not** from `os.environ` — and the LAN IP is detected with a UDP-socket probe.
The gate is fail-closed: an unset, empty, or non-matching `SSH_HOST`, or a failed
detection, denies. It runs once for the invoked subcommand in the group callback,
keyed on `ctx.invoked_subcommand` against a single host-only set — so it precedes
per-command argument parsing, and off-host even `itsup <host-only-cmd> --help` is
refused.

<!-- planned-change:itsup-logs-router -->
- **Host-only** (refused off-host, exit 1): `run`, `apply`, `down`, `dns`,
  `proxy`, `svc`, `monitor`. `make install-runtime` refuses off-host
  before it touches systemd/launchd (`bin/install-bringup.sh`).
<!-- change:itsup-logs-router -->
- **Host-only** (refused off-host, exit 1): `run`, `apply`, `down`, `dns`,
  `proxy`, `svc`, `monitor`, `logs`. `make install-runtime` refuses off-host
  before it touches systemd/launchd (`bin/install-bringup.sh`).
<!-- /planned-change:itsup-logs-router -->

- **Available anywhere** (GitOps + config + secrets + read): `pull`, `commit`,
  `status`, `create`, `init`, `validate`, `migrate`, `encrypt`, `decrypt`,
  `diff-secrets`, `edit-secret`, `sops-key`, `projects`.


The gate is not self-grantable: there is no bypass flag or override env var, and
the refusal message advertises no escape hatch. The allow/deny split lives in one
place. (`itsup/cli.py`, `lib/host_gate.py`)

### Secret loading context

- Each deploy/secret command loads secrets for **one context only** (project
  secrets for a project deploy; `itsup` infra secrets otherwise) — they are never
  merged — and prefers `*.enc.txt` over `*.txt`. Full contract:
  `project/spec/secrets-management`. (`lib/data.py:34`)

### Discovery & authoring (agent GitOps)

- `itsup projects` prints the configured project names, one per line, to
  stdout — the discovery entry point before listing or editing a project's
  files. `itsup projects <name>` prints the files that constitute the project:
  every regular file recursively below `projects/<name>/`, deterministically
  sorted, plus the project's `secrets/<name>.{enc.txt|txt}` when present, one
  per line. An unknown name exits 1. Both forms are read-only and sit on the anywhere-allowed side of
  the host gate.
- Every file location the CLI reports is usable from the caller's cwd: printed
  absolute when the process cwd is not the install root, and may stay relative
  when it is (`commands/common.py`). This includes `decrypt`, which reports
  each plaintext file it writes.
- `commit` is non-interactive: plaintext `secrets/*.txt` files present at
  commit time are encrypted in-process (plaintext deleted on success) before
  committing; when SOPS is unavailable while plaintext exists, `commit` fails
  with exit 1 instead of committing — a plaintext edit is never silently
  dropped by the `secrets/` gitignore. `--force` only skips the rebase and
  force-pushes; it never skips encryption.
- `edit-secret` is interactive and human-only: without a TTY on stdin it
  refuses (exit 1) and prints the non-interactive round-trip
  (`decrypt` → edit → `encrypt --delete` → `commit`).
- The intended agent workflow is discoverable from the CLI itself: the group
  help names the GitOps flow (pull before editing; re-encrypt before commit).

## Allowed values

### Exit codes (codified contract)

The CLI emits only these — there is no 2/3/130 contract.

- **0** — success.
- **1** — validation failure, target not found, or a handled command error
  (`sys.exit(1)`).
- **passed-through subprocess returncode** — `run`/`down`/`svc` and similar
  surface the failing `docker`/script returncode directly (`sys.exit(e.returncode)`).
- **`diff-secrets` is diff-style**: exits **1 when differences are found**, **0
  when identical** (`commands/diff_secrets.py:144`).

## Known caveats

- `apply` deploys projects **sequentially in egress-topological order**
  (`commands/apply.py`), not in parallel.
- Change detection compares the live `docker compose config` hash against the
  running container's `com.docker.compose.config-hash` label (container-label
  based), not a hash stored on disk.
<!-- planned-change:itsup-logs-router -->
- Runtime-mutating commands (`run`, `apply`, `down`, `dns`, `proxy`, `svc`,
  `monitor`) are **host-only** and refuse fail-closed off-host (detected
  LAN IP ≠ `SSH_HOST`); see the host-identity gate above. (`itsup logs` is
  removed; diagnostic logs are viewed with `instrukt-ai-logs itsup`.)
<!-- change:itsup-logs-router -->
- Runtime-mutating commands (`run`, `apply`, `down`, `dns`, `proxy`, `svc`,
  `monitor`) and the read-only `logs` router are **host-only** and refuse
  fail-closed off-host (detected LAN IP ≠ `SSH_HOST`); see the host-identity
  gate above. `logs` is gated not because it mutates but because every backend
  it reads exists only on the container host.
<!-- /planned-change:itsup-logs-router -->


## See Also

- docs/project/design/itsup-cli.md
- docs/project/spec/secrets-management.md
- docs/project/design/deployment-orchestration.md
