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
- **Host identity is a location gate, not operational authorization.** Passing the host check
  proves that a runtime command would act on the intended deployment host. Whether that command
  is appropriate still follows from the task, the observed failure, and the runtime-operation
  contract.
- **Remote host access remains an operating capability.** An operator or agent may connect to
  the container host for read-only diagnosis and evidence-based recovery. The remote connection
  does not weaken the host boundary: runtime commands still execute on the host, against its
  configured stack.

## Rationale

itsUP manages one running stack on one host. Running a runtime-mutating command off-host has no
remote target — it deploys locally, provisioning the whole stack (dozens of containers) on a
machine meant only for editing config. Keeping runtime mutation on the host and pushing all
change through git preserves the single-source-of-truth, single-reconciler model: config is safe
to edit anywhere, and only the host touches the runtime. Keeping location separate from
authorization preserves remote troubleshooting without treating technical availability as a
reason to intervene.

## Scope

- All agents and operators driving the `itsup` CLI, on any machine.
- The `itsup` CLI runtime-mutating commands and `make install-runtime`.

## Enforcement

- The operating discipline off-host is to use only the GitOps/config/read subset above and let
  the host reconcile.
- Running `itsup apply` (or another runtime-mutating command) on a non-host machine is a
  defect — it provisions the stack on the wrong machine.
- Desired-state authoring stays on the GitOps path unless an observed reconciliation failure
  starts operational recovery. Remote reachability alone is not failure evidence; runtime
  intervention uses the narrowest action that addresses the verified cause.

## Exceptions

- On the container host, the full command set is available for normal automation,
  troubleshooting, and recovery. Availability does not bypass the evidence and blast-radius
  discipline of the runtime-operation contract.
