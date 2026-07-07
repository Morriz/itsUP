---
description: The agent-facing itsUP CLI command surface — the commands an agent uses to operate a deployment, grouped by where they may run.
---
# itsUP CLI Surface — Spec

## What it is

The `itsup` CLI is the agent-facing operating surface for an itsUP deployment. It is installed
once per machine and runs from any working directory, always operating on its single install
root. The commands below are the surface an agent uses; exact arguments and flags come from
`itsup <command> --help`, which is the authoritative, always-current source.

Commands split by where they may run (see itsUP Host Boundary). The safe change sequence is in
the itsUP GitOps Workflow procedure.

## Canonical fields

Runs anywhere — GitOps, config, secrets, and read:

<!-- planned:itsup-agent-authoring-surface -->
- `itsup list-projects` — list the names of all configured projects.
- `itsup list-project-files <name>` — list the files that constitute a project, as paths
  usable from any working directory.
<!-- /planned:itsup-agent-authoring-surface -->
- `itsup pull` — rebase the `projects/` and `secrets/` repos onto their remotes.
- `itsup status` — git status of both repos.
- `itsup commit` — commit and push both repos.
- `itsup create <name>` — scaffold a new project (`itsup-project.yml`, `docker-compose.yml`,
  empty secrets file).
- `itsup init` — initialize the `projects/` and `secrets/` repos from samples.
- `itsup validate [project]` — validate project configuration and cross-project invariants
  (fail-closed).
- `itsup migrate` — migrate configuration schema to the latest version.
- `itsup decrypt [name]` — decrypt `secrets/<name>.enc.txt` to plaintext for editing.
- `itsup encrypt [name] [--delete]` — re-encrypt plaintext secrets; `--delete` removes plaintext.
- `itsup edit-secret <name>` — interactive, human-only (opens a terminal editor; blocks an
  agent — use `decrypt`/`encrypt` instead).
- `itsup diff-secrets` — show meaningful diffs of encrypted secrets.
- `itsup sops-key` — generate or rotate the SOPS encryption key.

Container host only — runtime-mutating (see itsUP Host Boundary):

- `itsup apply [project]` — regenerate artifacts and deploy with zero-downtime rollout.
- `itsup run` — bring up the itsUP stack (dns, proxy, monitor).
- `itsup down` — stop all containers.
- `itsup dns` / `itsup proxy` — DNS and proxy stack management.
- `itsup svc <project> <command>` — service operations for a project.
- `itsup monitor` — container security monitor management. Diagnostics are viewed via
  `instrukt-ai-logs itsup --include monitor`, not a subcommand.

## Known caveats

- A command listed here is not necessarily runnable on the current machine — runtime-mutating
  commands refuse off-host.
- Non-obvious per-command semantics (orchestration order, exit codes) live in `--help` and the
  project-level itsUP CLI spec, not restated here.
- This list is maintained by hand; `itsup <command> --help` is authoritative when they differ.
