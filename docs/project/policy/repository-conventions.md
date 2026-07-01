---
description: 'Standing working conventions for the itsUP repository: apply runs only on the container host, operate from repo root, itsUP code is never containerized, and the fixed pre-commit order.'
visibility: 'internal'
---

# Repository Conventions — Policy

## Rules

- **`itsup apply` runs only on the container host** — the machine whose own IP equals `SSH_HOST` in `.env`. Apply has no remote target; it deploys from inside the repo on that host. Never run it on any other machine (e.g. a dev laptop) — it would spin up the entire stack locally. Operational detail lives in `project/spec/runtime-operations`.
- **Operate from the repository root.** Never stay `cd`'d into a subdirectory. For directory-scoped work use `(cd <dir> && <command>)` with relative paths.
- **itsUP's own code is not containerized.** The Python CLI (`itsup`), API server, monitoring, DNS honeypot-management, and proxy-config code all run on the host. Only upstream project services are containerized. Never containerize itsUP code.
- **Pre-commit order is fixed:** `bin/format.sh` → `bin/lint.sh` → `bin/test.sh`. Run `bin/format.sh` before committing to avoid format-then-fail loops in the hook.

## Rationale

- Each rule encodes an itsUP-specific footgun: `apply` has no remote target, so running it off-host spins a full local stack; the repo is operated as a single rooted tree, so subdir-relative commands drift; itsUP is the orchestrator, not a containerized workload; and the pre-commit order is fixed so formatting never fights the linter.

## Scope

- Applies to all agents and developers working in the itsUP repository.

## Enforcement

- Running `itsup apply` anywhere but the container host is a defect.
- Containerizing any itsUP code path is a defect.
- Committing without first running `bin/format.sh` risks a formatting loop in pre-commit.

## Exceptions

- None.
