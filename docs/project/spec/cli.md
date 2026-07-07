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

- **Host-only** (refused off-host, exit 1): `run`, `apply`, `down`, `dns`,
  `proxy`, `svc`, `monitor`. `make install-runtime` refuses off-host
  before it touches systemd/launchd (`bin/install-bringup.sh`).

- **Available anywhere** (GitOps + config + secrets + read): `pull`, `commit`,
  `status`, `create`, `init`, `validate`, `migrate`, `encrypt`, `decrypt`,
  `diff-secrets`, `edit-secret`, `sops-key`.

The gate is not self-grantable: there is no bypass flag or override env var, and
the refusal message advertises no escape hatch. The allow/deny split lives in one
place. (`itsup/cli.py`, `lib/host_gate.py`)

### Secret loading context

- Each deploy/secret command loads secrets for **one context only** (project
  secrets for a project deploy; `itsup` infra secrets otherwise) — they are never
  merged — and prefers `*.enc.txt` over `*.txt`. Full contract:
  `project/spec/secrets-management`. (`lib/data.py:34`)

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
- Runtime-mutating commands (`run`, `apply`, `down`, `dns`, `proxy`, `svc`,
  `monitor`) are **host-only** and refuse fail-closed off-host (detected
  LAN IP ≠ `SSH_HOST`); see the host-identity gate above. (`itsup logs` is
  removed; diagnostic logs are viewed with `instrukt-ai-logs itsup`.)


## See Also

- docs/project/design/itsup-cli.md
- docs/project/spec/secrets-management.md
- docs/project/design/deployment-orchestration.md
