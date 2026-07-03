---
description: The safe sequence for an agent to change itsUP deployment config — pull, edit projects/secrets, validate, re-encrypt, commit — after which the container host reconciles.
activation_trigger: Use when asked to create, edit, or remove an itsUP project or secret, or otherwise change what itsUP deploys.
---
# itsUP GitOps Workflow — Procedure

## Goal

Change what itsUP deploys — add or edit a project, change routing, or update a secret — safely,
from any machine, so the container host reconciles the running stack to the new desired state.

## Preconditions

- The `itsup` CLI is installed and on PATH (it runs from any working directory).
- The change is a configuration or secret change (desired state), not a runtime operation.
  Runtime-mutating commands run only on the container host (see itsUP Host Boundary).

## Steps

1. **Pull first.** Run `itsup pull` to rebase both the `projects/` and `secrets/` repos onto
   their remotes before editing. This keeps local config current with what the host last
   reconciled and avoids diverging. Conflicts are rare; if a rebase conflicts, `itsup pull`
   reports it for manual resolution.

2. **Create or locate the project.** For a new project, `itsup create <name>` scaffolds
   `projects/<name>/itsup-project.yml`, `projects/<name>/docker-compose.yml`, and an empty
   `secrets/<name>.txt`. For an existing project, edit the files under the install root's
   `projects/<name>/`.

3. **Edit the declarative files.** Edit `itsup-project.yml` (routing) and `docker-compose.yml`
   (services) directly. Define only services in compose — itsUP injects routing, labels,
   networks, and DNS.

4. **Edit secrets non-interactively.** To change a secret, `itsup decrypt <name>` writes the
   plaintext `secrets/<name>.txt`; edit it, then `itsup encrypt <name> --delete` re-encrypts to
   `<name>.enc.txt` and removes the plaintext. Do not use `itsup edit-secret` from an agent — it
   opens an interactive editor and blocks.

5. **Validate.** Run `itsup validate` to check every project's configuration and cross-project
   invariants before committing. Validation is fail-closed — one invalid project blocks a host
   apply.

6. **Re-encrypt before committing.** Confirm no plaintext `secrets/*.txt` remains un-encrypted.
   Plaintext is gitignored, so an unencrypted edit is silently omitted from the commit and lost;
   re-encrypt (step 4) first.

7. **Commit and push.** Run `itsup commit` to commit and push both repos. The container host
   reconciles from git (on its own schedule or via its reconcile webhook); the change is live
   once the host applies it.

## Outputs

- The `projects/` and `secrets/` repos hold the new desired state and are pushed to their
  remotes.
- The container host reconciles the running stack to match.

## Recovery

- **Rebase conflict on pull or commit:** resolve in the affected repo (`projects/` or
  `secrets/`) and re-run the command.
- **Validation fails:** fix the reported project(s); do not commit invalid config — the host
  refuses to apply it.
- **A secret edit did not take effect after deploy:** confirm the plaintext was re-encrypted
  (`itsup encrypt <name> --delete`) before the commit — an unencrypted edit is not committed.
