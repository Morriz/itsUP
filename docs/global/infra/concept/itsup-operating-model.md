---
description: How any agent operates a running itsUP deployment — declarative config in two git repos, a single container host that reconciles from git, and a location-transparent CLI.
---
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
