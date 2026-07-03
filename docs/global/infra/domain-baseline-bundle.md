# infra — Platform Baseline

# itsUP Operating Model — Concept

## What

itsUP is a GitOps deployment platform. The desired state of every deployed service lives as
declarative configuration in git, and a single machine — the **container host** — reconciles
the running stack to match that configuration. Agents change what is deployed by editing
configuration and committing it; they do not operate containers directly.

Two git repositories hold all desired state, both nested under the itsUP install root and each
pushed to its own remote:

- **`projects/`** — one directory per deployed project, declaring routing and services.
- **`secrets/`** — SOPS/age-encrypted secrets, one encrypted file per project.

The `itsup` CLI is the operating surface. It is installed once per machine and runs from **any
working directory**: it always resolves its single install root — never the current directory —
and operates on that one deployment. An agent therefore never needs to `cd` into the repo to
drive itsUP. The files it edits still live under that root (see itsUP Projects and Secrets).

Work splits across two machine roles:

- **The container host** — the machine whose own LAN IP equals `SSH_HOST` in `.env` — runs the
  stack and reconciles it. Runtime-mutating commands (`apply`, `run`, `down`, …) belong here.
- **Any other machine** (e.g. a developer laptop mirroring the config) is for GitOps only: edit
  config and secrets, validate, commit. The host picks up the change and reconciles.

## Why

Separating desired state (git) from the running stack (one host) gives the deployment a single
source of truth and a single reconciler. An agent editing config on a laptop cannot destabilize
the running stack — the worst it can do is push a bad commit, which validation catches before
the host applies it. Committing is safe from anywhere; only the host mutates the runtime.

A location-transparent CLI exists because the operator is an agent, not a human sitting in the
repo. The agent invokes `itsup` from wherever it happens to be and the CLI resolves the one
deployment it manages. This is why itsUP binds to exactly one install root rather than selecting
a project from the current directory.

## See Also

- ~/.teleclaude/docs/infra/concept/itsup-project-and-secrets.md
- ~/.teleclaude/docs/infra/procedure/itsup-gitops-workflow.md
- ~/.teleclaude/docs/infra/policy/itsup-host-boundary.md

---

# itsUP Projects and Secrets — Concept

## What

A **project** is the unit of deployment: a single directory in the `projects/` git repo, named
for the project, holding a small, predictable set of files.

- **`itsup-project.yml`** — routing declaration in itsUP's own schema: whether the project is
  enabled, its ingress (service, router, port, domain), egress, and TLS.
- **`docker-compose.yml`** — the service definition(s) as raw Docker Compose. It defines only
  the services; itsUP injects routing, Traefik labels, networks, and DNS when it generates the
  deployable stack.
- **Optional bind-mount directories** (e.g. `config/`, `certs/`) — project-specific files the
  services mount. Service state is bind-mounted, never kept in named volumes.

A **secret** is one file per project in the separate `secrets/` git repo:

- **`<project>.enc.txt`** — SOPS/age-encrypted key/value secrets. This is the only tracked form.
- **`<project>.txt`** — the decrypted plaintext, produced transiently for editing. It is
  gitignored and never committed.

That is the whole surface. To add or change a deployed service, an agent edits these files and
commits — nothing else constitutes a project. Both repos live under the itsUP install root, so
an agent editing the files directly works against their real paths under that root.

## Why

Keeping a project to two declarative files plus one encrypted secret makes "edit a project" a
closed, predictable operation an agent can perform without rediscovering bespoke structure each
time. Routing lives in `itsup-project.yml` and services in `docker-compose.yml` so the compose
input can come straight from a vendor's published stack while itsUP owns all the infrastructure
wiring around it.

Secrets are encrypted at rest and decrypted only transiently because the repo is shared and
pushed to a remote. The plaintext form is gitignored so a decrypt-edit-commit cycle cannot leak
secrets into git history — but that same rule means an un-encrypted edit is invisible to git and
must be re-encrypted before it is committed, or it is silently lost.

## See Also

- ~/.teleclaude/docs/infra/procedure/itsup-gitops-workflow.md
- ~/.teleclaude/docs/infra/concept/itsup-operating-model.md

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
