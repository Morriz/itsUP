---
description: Which itsUP CLI commands may run on which machine — runtime-mutating commands only on the container host, GitOps and read commands anywhere.
---
# itsUP Host Boundary — Policy

## Rules

- **Runtime-mutating commands run only on the container host** — the machine whose own LAN IP
  equals `SSH_HOST` in `.env`. These deploy or stop containers: `apply`, `run`, `down`, and the
  stack-management commands (`dns`, `proxy`, `svc`, `monitor`, `logs`), plus host provisioning
  (`make install-runtime`). On the host, the full command set is available.
- **GitOps, config, secret, and read commands run anywhere.** `pull`, `commit`, `status`,
  `create`, `init`, `validate`, `migrate`, `edit-secret`, `encrypt`, `decrypt`, `diff-secrets`,
  and `sops-key` operate on git-tracked desired state and are safe on any machine.
- **Off-host, change deployment through git, never through the runtime.** On a non-host machine
  (e.g. a laptop mirroring the config), edit config and secrets, `itsup validate`, and
  `itsup commit`; the container host reconciles the change. Do not run `apply`/`run`/`down`
  off-host — they would spin up the entire stack locally on a machine that only mirrors the
  config.
- **The boundary keys on host identity, not project names.** Because a laptop may run many
  same-named stacks locally, the host is identified by its LAN IP matching `SSH_HOST`, never by
  container or project names.

## Rationale

itsUP manages one running stack on one host. Running a runtime-mutating command off-host has no
remote target — it deploys locally, provisioning the whole stack (dozens of containers) on a
machine meant only for editing config. Keeping runtime mutation on the host and pushing all
change through git preserves the single-source-of-truth, single-reconciler model: config is safe
to edit anywhere, and only the host touches the runtime.

## Scope

- All agents and operators driving the `itsup` CLI, on any machine.
- The `itsup` CLI runtime-mutating commands and `make install-runtime`.

## Enforcement

- The operating discipline off-host is to use only the GitOps/config/read subset above and let
  the host reconcile.
- Running `itsup apply` (or another runtime-mutating command) on a non-host machine is a
  defect — it provisions the stack on the wrong machine.

## Exceptions

- On the container host, the full command set is available, including runtime mutation — the
  on-host agent sometimes needs it (e.g. bringing a stack down to fix it).
