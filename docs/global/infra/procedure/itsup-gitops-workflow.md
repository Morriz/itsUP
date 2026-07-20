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

2. **Create or locate the project.** For a new project, `itsup create <name>` scaffolds its
   files and prints their paths. For an existing project, `itsup projects` lists the
   configured project names and `itsup projects <name>` prints that project's files as paths
   usable from any working directory — edit those.

3. **Edit the declarative files.** Edit `itsup-project.yml` (routing) and `docker-compose.yml`
   (services) directly. Define only services in compose — itsUP injects routing, labels,
   networks, and DNS. Multi-line container logic never lives inline in compose YAML: write it
   to a script file in the project folder, mount it read-only into the service, and invoke
   it — inline `command` strings are for one-liners only.

4. **Edit secrets non-interactively.** To change a secret, `itsup decrypt <name>` writes the
   plaintext `secrets/<name>.txt` and prints its path (usable from any working directory); edit
   it, then `itsup encrypt <name> --delete` re-encrypts to `<name>.enc.txt` and removes the
   plaintext. Do not use `itsup edit-secret` from an agent — it opens an interactive editor and
   blocks.

5. **Validate.** Run `itsup validate` to check every project's configuration and cross-project
   invariants before committing. Validation is fail-closed — one invalid project blocks a host
   apply.

6. **Re-encrypt before committing.** Re-encrypt any edited secret with `itsup encrypt <name>
   --delete` before committing. Plaintext is gitignored, so an unencrypted edit would be omitted
   from the commit; `itsup commit` refuses when un-encrypted `secrets/*.txt` remain, so a
   forgotten re-encryption fails loud instead of silently losing the edit.

7. **Commit and push.** Run `itsup commit` to commit and push both repos. A push to the
   projects or secrets repo triggers a host reconcile through the shared GitHub Actions
   workflow (`Reconcile itsUP`), with the nightly apply as the scheduled backstop; the
   change is live once the host applies it. Verify the triggered run succeeded (`gh run
   list` on the config repo) rather than assuming it. This is the normal completion point
   for desired-state authoring; do not follow a successful push with a manual apply merely
   to accelerate or observe reconciliation.

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
- **Automated reconciliation failed:** inspect the pipeline and host evidence before mutating
  runtime state. A targeted `itsup apply <project>` on the container host may recover the
  committed desired state when reconciliation has actually failed; it is not the routine next
  step after a push.
- **Recovery required manual mutation:** record the failed reconciliation, the intervention,
  and its outcome. Report a bug when the intervention reveals a platform defect or missing
  recovery behavior; read-only troubleshooting alone is not a bug signal.

## Discipline

GitOps is the normal deployment path, while live operations remain available for diagnosis and
recovery. Do not confuse a reachable host with a reason to intervene, and do not confuse a
delayed reconciliation with a failed one. Once failure is evidenced, diagnose first and use the
narrowest action that addresses the verified cause. Manual mutation beyond the normal GitOps
path is exceptional evidence that may belong in a bug report.
